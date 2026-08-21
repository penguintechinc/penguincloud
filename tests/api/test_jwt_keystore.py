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

Round 1 review findings addressed here
=======================================
* **I1** — the first version of this fix only refused when
  ``DEPLOYMENT_REPLICAS > 1``, and NOTHING in this repository sets
  ``DEPLOYMENT_REPLICAS`` (the Helm chart is a stub, neither compose file
  declared it), so the guard was inert everywhere it mattered -- it failed
  OPEN. :class:`TestUndeclaredTopologyRefusesToStart` covers the fix: an
  UNDECLARED replica/worker count now refuses to start, not just a
  declared count above 1.
* **I3** — the failure domain is PROCESSES, not Kubernetes replicas.
  ``hypercorn --workers N`` calls ``create_app()`` once per OS process,
  each building its own ``MemoryKeyStore`` -- the identical bug, on a
  SINGLE pod. :class:`TestWorkerCountFoldedIntoTheCheck` covers
  ``HYPERCORN_WORKERS`` folding into the same guard multiplicatively with
  ``DEPLOYMENT_REPLICAS``.
* **M6** — a hand-authored keystore Secret written as ``{"keys": []}``
  (the exact shape docs/DEVELOPMENT.md's provisioning guidance can
  produce) loads successfully via ``FileKeyStore._load`` and only fails
  at the FIRST TOKEN MINT with a bare ``IndexError`` -- loud, but at the
  wrong moment. :class:`TestEmptyKeystoreFailsAtBootNotAtFirstMint`
  covers converting that into a boot-time ``RuntimeError``.

What "fixed" means here
========================
:class:`TestUndeclaredTopologyRefusesToStart` and
:class:`TestWorkerCountFoldedIntoTheCheck` are the actual regression
tests: each asserts NEW behaviour the ORIGINAL (round-1) code does not
provide. Run them against a checkout without this round's fix and
``pytest.raises`` fails with ``DID NOT RAISE``, because the original code
silently proceeds -- see the module-level revert-verification recorded in
this branch's commit history.

:class:`TestMemoryKeyStoresDoNotCrossVerify` demonstrates the underlying
mechanism the guard exists to prevent -- two apps that each, honestly,
declare themselves single-process still cannot verify each other's tokens
if someone runs two of them anyway. This class does not change behaviour
across the fix (MemoryKeyStore was never meant to be shared, before or
after), so it is not itself a "goes red before, green after" test -- it is
here as living documentation of why the guard matters, and as a fenced-off
baseline so nobody discovers by accident that the fix was to make
MemoryKeyStore somehow shared instead.

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


def _config_class(
    *,
    keystore_path: str = "",
    replicas: int = 1,
    replicas_declared: bool = True,
    workers: int = 1,
    workers_declared: bool = True,
) -> type[TestingConfig]:
    """Build a fresh ``TestingConfig`` subclass with keystore settings overridden.

    A distinct subclass per call (not mutating ``TestingConfig`` itself)
    keeps each app instance's config isolated from every other test and
    from every other app built within the same test. Defaults match
    ``TestingConfig``'s own explicit declaration (1 replica, 1 worker,
    both declared) so a bare ``_config_class()`` call reproduces an
    honestly-configured single process, matching the safe default state.
    """

    class _Cfg(TestingConfig):
        JWT_KEYSTORE_PATH = keystore_path
        DEPLOYMENT_REPLICAS = replicas
        DEPLOYMENT_REPLICAS_DECLARED = replicas_declared
        HYPERCORN_WORKERS = workers
        HYPERCORN_WORKERS_DECLARED = workers_declared

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


class TestUndeclaredTopologyRefusesToStart:
    """Round-1 I1: an UNDECLARED replica/worker count must refuse, not assume 1.

    Prior to this round, an unset ``DEPLOYMENT_REPLICAS`` was
    indistinguishable from an explicit ``DEPLOYMENT_REPLICAS=1`` -- both
    resolved to the same ``int`` and the guard only fired on ``> 1``. Since
    nothing in this repository sets the variable (Helm chart is a stub,
    neither compose file declared it), every real deployment silently took
    the "assume 1" branch. Run these against that code and each
    ``pytest.raises`` fails with "DID NOT RAISE RuntimeError".
    """

    def test_neither_declared_refuses(self) -> None:
        """Neither DEPLOYMENT_REPLICAS nor HYPERCORN_WORKERS declared -> refuse."""
        cfg = _config_class(replicas_declared=False, workers_declared=False)

        with pytest.raises(RuntimeError, match="never explicitly declared"):
            create_app(config_class=cfg)

    def test_only_replicas_declared_still_refuses(self) -> None:
        """Declaring one axis but not the other is still an undeclared topology."""
        cfg = _config_class(replicas_declared=True, workers_declared=False)

        with pytest.raises(RuntimeError, match="never explicitly declared"):
            create_app(config_class=cfg)

    def test_only_workers_declared_still_refuses(self) -> None:
        """Same as above, the other axis undeclared."""
        cfg = _config_class(replicas_declared=False, workers_declared=True)

        with pytest.raises(RuntimeError, match="never explicitly declared"):
            create_app(config_class=cfg)

    def test_both_declared_as_one_starts_fine(self) -> None:
        """The safe, fully-declared single-process case is unaffected."""
        cfg = _config_class(replicas_declared=True, workers_declared=True)

        app = create_app(config_class=cfg)

        assert app.extensions["oidc_provider"] is not None

    def test_shared_keystore_bypasses_the_declaration_requirement(self, tmp_path: Path) -> None:
        """A configured JWT_KEYSTORE_PATH makes the topology irrelevant."""
        cfg = _config_class(
            keystore_path=str(tmp_path / "keys.json"),
            replicas_declared=False,
            workers_declared=False,
        )

        app = create_app(config_class=cfg)

        assert app.extensions["oidc_provider"] is not None


class TestDeclaredMultiProcessRefusesToStart:
    """Declared >1 effective processes with no shared keystore still refuses."""

    def test_refuses_to_start_without_shared_keystore(self) -> None:
        """Declaring 3 replicas with no keystore path raises at app creation."""
        cfg = _config_class(keystore_path="", replicas=3)

        with pytest.raises(RuntimeError, match=r"DEPLOYMENT_REPLICAS=3 x HYPERCORN_WORKERS=1"):
            create_app(config_class=cfg)

    def test_error_message_names_the_fix(self) -> None:
        """The refusal names BOTH escape hatches, not just the defect."""
        cfg = _config_class(keystore_path="", replicas=2)

        with pytest.raises(RuntimeError) as exc_info:
            create_app(config_class=cfg)

        message = str(exc_info.value)
        assert "JWT_KEYSTORE_PATH" in message
        assert "DEPLOYMENT_REPLICAS=1" in message
        assert "HYPERCORN_WORKERS=1" in message

    def test_single_replica_is_unaffected(self) -> None:
        """1 declared replica x 1 declared worker never raises."""
        cfg = _config_class(keystore_path="", replicas=1)

        app = create_app(config_class=cfg)

        assert app.extensions["oidc_provider"] is not None

    def test_shared_keystore_with_multiple_replicas_does_not_raise(self, tmp_path: Path) -> None:
        """Declaring >1 replicas is fine once a shared keystore is configured."""
        cfg = _config_class(keystore_path=str(tmp_path / "keys.json"), replicas=5)

        app = create_app(config_class=cfg)

        assert app.extensions["oidc_provider"] is not None


class TestWorkerCountFoldedIntoTheCheck:
    """Round-1 I3: HYPERCORN_WORKERS folds into the same guard as DEPLOYMENT_REPLICAS.

    ``hypercorn --workers N`` calls ``create_app()`` once per OS process on
    a SINGLE pod -- ``DEPLOYMENT_REPLICAS=1`` alone said nothing about
    that axis before this round. Run these against a checkout that only
    checks ``DEPLOYMENT_REPLICAS`` and each ``pytest.raises`` fails with
    "DID NOT RAISE RuntimeError".
    """

    def test_multiple_workers_alone_refuses(self) -> None:
        """1 replica x 4 workers = 4 processes, no shared keystore -> refuse."""
        cfg = _config_class(keystore_path="", replicas=1, workers=4)

        with pytest.raises(RuntimeError, match=r"DEPLOYMENT_REPLICAS=1 x HYPERCORN_WORKERS=4"):
            create_app(config_class=cfg)

    def test_replicas_times_workers_multiplies(self) -> None:
        """2 replicas x 3 workers = 6 effective processes, named in the error."""
        cfg = _config_class(keystore_path="", replicas=2, workers=3)

        with pytest.raises(RuntimeError, match=r"= 6 processes"):
            create_app(config_class=cfg)

    def test_single_replica_single_worker_is_unaffected(self) -> None:
        """1 x 1 = 1 effective process -- the only case that may fall back."""
        cfg = _config_class(keystore_path="", replicas=1, workers=1)

        app = create_app(config_class=cfg)

        assert app.extensions["oidc_provider"] is not None

    def test_shared_keystore_with_multiple_workers_does_not_raise(self, tmp_path: Path) -> None:
        """A configured JWT_KEYSTORE_PATH makes the worker count irrelevant."""
        cfg = _config_class(keystore_path=str(tmp_path / "keys.json"), replicas=1, workers=8)

        app = create_app(config_class=cfg)

        assert app.extensions["oidc_provider"] is not None


class TestEmptyKeystoreFailsAtBootNotAtFirstMint:
    """Round-1 M6: a keystore file that parses but holds zero keys must refuse at boot.

    ``FileKeyStore._load`` (penguin_aaa/crypto/keystore.py:196-204) reads
    an existing file's ``"keys"`` list as-is -- an empty list loads
    successfully. ``get_signing_key()`` then returns ``self._keys[-1]``,
    which raises a bare ``IndexError`` -- but only the first time a token
    is minted, not at startup. Run this against a checkout without the
    boot-time probe and ``pytest.raises(RuntimeError)`` fails because
    ``create_app()`` does not raise there at all (the ``IndexError`` would
    only surface later, from a completely different call site this test
    never reaches).
    """

    def test_zero_keys_refuses_at_create_app_not_later(self, tmp_path: Path) -> None:
        """A hand-authored {"keys": []} file is refused at app creation."""
        keystore_path = tmp_path / "empty-keys.json"
        keystore_path.write_text('{"keys": []}', encoding="utf-8")
        cfg = _config_class(keystore_path=str(keystore_path))

        with pytest.raises(RuntimeError, match="zero signing keys"):
            create_app(config_class=cfg)

    def test_a_real_key_in_the_file_starts_fine(self, tmp_path: Path) -> None:
        """The boot-time probe does not reject a genuinely populated keystore."""
        keystore_path = str(tmp_path / "keys.json")
        # First construction self-bootstraps (see docs/DEVELOPMENT.md's
        # FileKeyStore write-up) -- build once directly to populate the
        # file with a real key, exactly as a provisioning step would.
        from penguin_aaa.crypto.keystore import FileKeyStore

        FileKeyStore(Path(keystore_path))
        cfg = _config_class(keystore_path=keystore_path)

        app = create_app(config_class=cfg)

        assert app.extensions["oidc_provider"] is not None


class TestMemoryKeyStoresDoNotCrossVerify:
    """Documents the mechanism: independent MemoryKeyStores never interoperate.

    Both apps here are HONESTLY configured (1 declared replica, 1 declared
    worker, its safe default) -- this is what happens if an operator runs
    two such processes anyway without telling either about the other. It
    is the scenario the guards above exist to catch before it reaches
    production, demonstrated directly at the token level.
    """

    def test_token_minted_by_one_process_rejected_by_another(self) -> None:
        """A token minted on app_a's key is rejected by app_b's independent key."""
        cfg = _config_class()  # keystore_path="", 1 declared replica, 1 declared worker
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
    """DEPLOYMENT_REPLICAS/HYPERCORN_WORKERS default to 1, declared, in TestingConfig."""
    assert TestingConfig.DEPLOYMENT_REPLICAS == 1
    assert TestingConfig.DEPLOYMENT_REPLICAS_DECLARED is True
    assert TestingConfig.HYPERCORN_WORKERS == 1
    assert TestingConfig.HYPERCORN_WORKERS_DECLARED is True
