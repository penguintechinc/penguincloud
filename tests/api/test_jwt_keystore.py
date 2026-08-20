"""Regression coverage for the multi-replica JWT signing-keystore defect.

The bug, precisely
===================
``app/__init__.py:_build_oidc_provider`` used an in-process
``MemoryKeyStore`` whenever ``JWT_KEYSTORE_PATH`` was unset, with no
enforcement that this only happens for a genuinely single-process
deployment. Two Quart processes built this way each generate their OWN
signing key: a token minted by one is signed with a private key the other
never saw, so ``middleware.auth_required``'s verification -- kid lookup
against ``oidc.jwks()``, then ``pyjwt.decode`` against the matching public
key -- fails with ``401 Invalid token - key not found``. Run more than one
replica of the same deployment (``devops-kubernetes.md`` requires 3+ in
production) and this is not an outage: it is an intermittent 401 that
tracks load-balancer routing, reproduces only under multi-replica, and
disappears the instant anyone tests against a single pod.

What "fixed" means here
========================
:class:`TestUndeclaredMultiReplicaRefusesToStart` is the actual regression
test: it asserts the NEW behaviour (loud refusal at boot) that the ORIGINAL
code does not provide -- run it against a checkout without the
``DEPLOYMENT_REPLICAS`` guard and ``pytest.raises`` fails with
``DID NOT RAISE``, because the original code silently proceeds. That is
the "revert the fix and watch it go red" case.

:class:`TestMemoryKeyStoresDoNotCrossVerify` demonstrates the underlying
mechanism the guard exists to prevent -- two apps that each, honestly,
declare themselves single-replica (``DEPLOYMENT_REPLICAS`` at its default
of 1) still cannot verify each other's tokens if someone runs two of them
anyway. This class does not change behaviour across the fix (MemoryKeyStore
was never meant to be shared, before or after), so it is not itself a
"goes red before, green after" test -- it is here as living documentation
of why the guard in the first class matters, and as a fenced-off baseline
so nobody discovers by accident that the fix was to make MemoryKeyStore
somehow shared instead.

:class:`TestSharedFileKeystoreLetsReplicasVerify` is the "or a shared key"
half of the brief: two independently constructed apps pointed at the SAME
``JWT_KEYSTORE_PATH`` load the SAME signing key and DO cross-verify.

:class:`TestMemoryKeyStoreChoiceIsAnnounced` covers the "deliberate,
visible decision" requirement -- falling back to ``MemoryKeyStore`` must
log a WARNING naming the consequence, not silently proceed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt as pyjwt
import pytest
from app import create_app
from app.config import TestingConfig
from jwt import PyJWK
from penguin_aaa.authn.oidc_provider import OIDCProvider
from penguin_aaa.authn.types import Claims
from quart import Quart


def _config_class(*, keystore_path: str = "", replicas: int = 1) -> type[TestingConfig]:
    """Build a fresh ``TestingConfig`` subclass with keystore settings overridden.

    A distinct subclass per call (not mutating ``TestingConfig`` itself)
    keeps each app instance's config isolated from every other test and
    from every other app built within the same test.
    """

    class _Cfg(TestingConfig):
        JWT_KEYSTORE_PATH = keystore_path
        DEPLOYMENT_REPLICAS = replicas

    return _Cfg


def _claims(tenant: str = "tenant-a") -> Claims:
    now = datetime.now(UTC)
    return Claims(
        sub="42",
        iss="https://penguincloud-test.localhost.local",
        aud=["penguincloud-test-client"],
        iat=now,
        exp=now + timedelta(minutes=30),
        scope=["read"],
        tenant=tenant,
    )


def _mint(app: Quart) -> str:
    """Mint an access token from the app's own OIDC provider."""
    oidc: OIDCProvider = app.extensions["oidc_provider"]
    token_set = oidc.issue_token_set(_claims())
    return str(token_set.access_token)


def _verifies(verifier_app: Quart, token: str) -> bool:
    """Replay ``middleware.auth_required``'s own verification path.

    Kid lookup against the verifier's JWKS, then signature verification --
    the exact sequence app/middleware.py uses, so this proves the real
    request path, not a hand-rolled stand-in for it (see
    feedback-revert-verification: a test double that mirrors the
    implementation's assumption cannot falsify it).
    """
    oidc = verifier_app.extensions["oidc_provider"]
    header = pyjwt.get_unverified_header(token)
    kid = header.get("kid")

    public_key_data = None
    for key_data in oidc.jwks().get("keys", []):
        if key_data.get("kid") == kid:
            public_key_data = PyJWK.from_dict(key_data).key
            break

    if public_key_data is None:
        return False

    try:
        pyjwt.decode(
            token,
            public_key_data,
            algorithms=["RS256", "ES256", "ES384", "ES512"],
            issuer=verifier_app.config["JWT_ISSUER"],
            audience=list(verifier_app.config["JWT_AUDIENCES"]),
        )
    except pyjwt.InvalidTokenError:
        return False
    return True


class TestUndeclaredMultiReplicaRefusesToStart:
    """The actual regression test: loud refusal beats a silent per-replica key.

    Prior to this fix, ``DEPLOYMENT_REPLICAS`` did not exist and
    ``create_app`` never raised here -- it silently built a MemoryKeyStore
    regardless of intended replica count. Run this against that code and
    ``pytest.raises`` fails with "DID NOT RAISE RuntimeError", which is the
    failing (red) run this test is required to have had.
    """

    def test_refuses_to_start_without_shared_keystore(self) -> None:
        """Declaring >1 replicas with no keystore path raises at app creation."""
        cfg = _config_class(keystore_path="", replicas=3)

        with pytest.raises(RuntimeError, match="DEPLOYMENT_REPLICAS=3"):
            create_app(config_class=cfg)

    def test_error_message_names_the_fix(self) -> None:
        """The refusal names BOTH escape hatches, not just the defect."""
        cfg = _config_class(keystore_path="", replicas=2)

        with pytest.raises(RuntimeError) as exc_info:
            create_app(config_class=cfg)

        message = str(exc_info.value)
        assert "JWT_KEYSTORE_PATH" in message
        assert "DEPLOYMENT_REPLICAS=1" in message

    def test_single_replica_is_unaffected(self) -> None:
        """DEPLOYMENT_REPLICAS<=1 (the default) never raises -- dev/tests are safe."""
        cfg = _config_class(keystore_path="", replicas=1)

        app = create_app(config_class=cfg)

        assert app.extensions["oidc_provider"] is not None

    def test_shared_keystore_with_multiple_replicas_does_not_raise(self, tmp_path: Path) -> None:
        """Declaring >1 replicas is fine once a shared keystore is configured."""
        cfg = _config_class(keystore_path=str(tmp_path / "keys.json"), replicas=5)

        app = create_app(config_class=cfg)

        assert app.extensions["oidc_provider"] is not None


class TestMemoryKeyStoresDoNotCrossVerify:
    """Documents the mechanism: independent MemoryKeyStores never interoperate.

    Both apps here are HONESTLY configured (DEPLOYMENT_REPLICAS defaults to
    1, its safe default) -- this is what happens if an operator runs two
    such processes anyway without telling either about the other. It is
    the scenario the guard in TestUndeclaredMultiReplicaRefusesToStart
    exists to catch before it reaches production, demonstrated directly at
    the token level.
    """

    def test_token_minted_by_one_process_rejected_by_another(self) -> None:
        """A token minted on app_a's key is rejected by app_b's independent key."""
        cfg = _config_class()  # keystore_path="", replicas=1 -- both defaults
        app_a = create_app(config_class=cfg)
        app_b = create_app(config_class=cfg)

        token = _mint(app_a)

        assert _verifies(app_a, token) is True
        assert _verifies(app_b, token) is False


class TestSharedFileKeystoreLetsReplicasVerify:
    """The "or a shared key" outcome: same JWT_KEYSTORE_PATH, same signing key."""

    def test_token_minted_by_one_process_verifies_on_another(self, tmp_path: Path) -> None:
        """Two apps sharing JWT_KEYSTORE_PATH load the same key and cross-verify."""
        keystore_path = str(tmp_path / "shared-keys.json")
        cfg = _config_class(keystore_path=keystore_path, replicas=3)

        # Two INDEPENDENT app instances, standing in for two replicas that
        # never talk to each other except through the shared file.
        app_a = create_app(config_class=cfg)
        app_b = create_app(config_class=cfg)

        token = _mint(app_a)

        assert _verifies(app_a, token) is True
        assert _verifies(app_b, token) is True


class TestMemoryKeyStoreChoiceIsAnnounced:
    """Falling back to MemoryKeyStore must be visible, not just documented."""

    def test_warns_with_the_consequence_named(self, caplog: pytest.LogCaptureFixture) -> None:
        """Falling back to MemoryKeyStore logs a WARNING naming the consequence."""
        cfg = _config_class(keystore_path="", replicas=1)

        with caplog.at_level("WARNING", logger="app"):
            create_app(config_class=cfg)

        warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        matching = [m for m in warnings if "jwt_keystore_is_per_process_only" in m]
        assert matching, f"expected a jwt_keystore_is_per_process_only WARNING, got: {warnings}"
        assert "invalid signature" in matching[0]

    def test_shared_keystore_does_not_warn(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A configured JWT_KEYSTORE_PATH never triggers the per-process WARNING."""
        cfg = _config_class(keystore_path=str(tmp_path / "keys.json"), replicas=1)

        with caplog.at_level("WARNING", logger="app"):
            create_app(config_class=cfg)

        warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert not any("jwt_keystore_is_per_process_only" in m for m in warnings)


def test_config_default_is_single_replica() -> None:
    """DEPLOYMENT_REPLICAS defaults to 1 -- existing deployments are unaffected."""
    assert TestingConfig.DEPLOYMENT_REPLICAS == 1
