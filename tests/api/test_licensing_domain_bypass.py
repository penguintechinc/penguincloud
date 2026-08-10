"""The env-var license bypass is gone, and the domain bypass is the only one.

``license.py`` opened ``is_feature_enabled`` with::

    if not self.release_mode:
        return True

``RELEASE_MODE`` defaults to false, so every deployment that had not set it
— which is the default, and which is every dev, alpha and test environment
— had Professional and Enterprise features unlocked. general.md permits
exactly one bypass ("Bypass is domain-based ONLY — never via env vars, CLI
args, or config flags"), and SSO gates through this path, so the whole
Professional SSO surface was free for the price of an unset variable.

This file is the regression suite for that finding. It asserts three things
that must all hold together:

1. ``RELEASE_MODE`` — at any value — cannot unlock a feature.
2. The domain list CAN, and matches on a dot boundary
   (``evilpenguincloud.io`` is not ``penguincloud.io``).
3. **The mint side and the enforce side meet.** Every feature name a
   ``@require_feature`` gate spells is a name :data:`FEATURE_MIN_TIER` can
   grant, and every tier in the map is reachable. A gate nothing mints is a
   permanent 403; a tier nothing checks is decorative. Both have shipped in
   this repo before.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Final

import pytest
from quart import Quart

from app import licensing
from app.license import LicenseManager

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_APP_DIR: Final[Path] = _REPO_ROOT / "services" / "portal-api" / "app"

#: ``@require_feature("name")`` as it is written at a decoration site.
_REQUIRE_FEATURE_RE: Final[re.Pattern[str]] = re.compile(
    r"""@require_feature\(\s*["'](?P<feature>[a-z0-9_]+)["']""",
)


def _decorated_feature_names() -> dict[str, list[str]]:
    """``{feature name: [where it is gated]}`` across the whole app package."""
    found: dict[str, list[str]] = {}
    for path in sorted(_APP_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in _REQUIRE_FEATURE_RE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            found.setdefault(match.group("feature"), []).append(
                f"{path.relative_to(_REPO_ROOT)}:{line}"
            )
    return found


class TestNoEnvVarBypass:
    """RELEASE_MODE must not be able to unlock anything, in either state."""

    @pytest.mark.parametrize("release_mode", ["true", "false", "", "TRUE"])
    def test_release_mode_cannot_entitle_a_feature(
        self, release_mode: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No value of RELEASE_MODE grants a Professional feature.

        The removed code returned True for the ``"false"`` case — the
        default — so this parametrisation fails on the pre-fix source at
        three of its four values.
        """
        monkeypatch.setenv("RELEASE_MODE", release_mode)
        monkeypatch.delenv("LICENSE_KEY", raising=False)
        licensing.reset_client()

        assert licensing.is_feature_entitled_blocking("sso_integration") is False
        assert LicenseManager().is_feature_enabled("sso_integration") is False

    def test_the_source_carries_no_release_mode_short_circuit(self) -> None:
        """No entitlement path may branch on RELEASE_MODE again.

        Pinned against the source rather than behaviour because the defect
        was a single early ``return True``: a future author adding
        ``if not self.release_mode: return True`` back to a NEW entitlement
        helper would pass every behavioural test written against the old
        one. ``release_mode`` legitimately survives in ``validate()`` (does a
        failed validation kill startup) and ``checkin()`` (do we phone home),
        neither of which decides entitlement.

        Parsed with ``ast`` and with the docstring stripped, so the narrative
        record of the removed bypass — which necessarily quotes it — is not
        mistaken for the bypass itself.
        """
        tree = ast.parse((_APP_DIR / "license.py").read_text(encoding="utf-8"))
        bodies: list[ast.stmt] = []
        for node in ast.walk(tree):
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and node.name in ("is_feature_enabled", "is_feature_entitled"):
                statements = list(node.body)
                if ast.get_docstring(node) is not None:
                    statements = statements[1:]
                bodies.extend(statements)

        assert bodies, "neither entitlement method was found — parser is stale"

        for statement in bodies:
            referenced = {
                child.attr
                for child in ast.walk(statement)
                if isinstance(child, ast.Attribute)
            } | {
                child.id for child in ast.walk(statement) if isinstance(child, ast.Name)
            }
            assert "release_mode" not in referenced, (
                "an entitlement path branches on RELEASE_MODE again — that "
                "is the env-var license bypass general.md forbids"
            )

    def test_unknown_feature_names_deny(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A name absent from the tier map is refused, not waved through."""
        monkeypatch.delenv("LICENSE_KEY", raising=False)
        licensing.reset_client()

        assert licensing.is_feature_entitled_blocking("no_such_feature") is False


class TestDomainBypassBoundary:
    """The only bypass, and it matches on a dot boundary."""

    @pytest.mark.parametrize(
        "host",
        [
            "portal.penguincloud.io",
            "penguincloud.io",
            "penguincloud.io:8443",
            "portal.penguintech.cloud",
            "penguincloud.localhost.local",
            "PORTAL.PENGUINCLOUD.IO",
        ],
    )
    def test_managed_domains_are_exempt(self, host: str) -> None:
        assert licensing.host_is_license_exempt(host) is True

    @pytest.mark.parametrize(
        "host",
        [
            "evilpenguincloud.io",
            "penguincloud.io.attacker.example",
            "notpenguintech.cloud",
            "localhost",
            "127.0.0.1:8000",
            "customer.example.com",
            "",
            None,
        ],
    )
    def test_everything_else_is_gated(self, host: str | None) -> None:
        """Suffix matching without a dot boundary is the classic hole.

        ``evilpenguincloud.io``.endswith(``penguincloud.io``) is True, so a
        hand-rolled matcher that dropped the leading dot would hand an
        attacker-controlled domain a full license bypass.
        """
        assert licensing.host_is_license_exempt(host) is False

    @pytest.mark.asyncio
    async def test_bypass_fails_closed_outside_a_request(self, app: Quart) -> None:
        """Background work has no host to trust, so it gets no exemption."""
        assert licensing.current_host_is_license_exempt() is False

    @pytest.mark.asyncio
    async def test_exempt_host_unlocks_a_professional_feature(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The domain bypass is real, not merely present.

        Both halves matter: a bypass nothing exercises is as broken as one
        that is always on, and the pre-fix code passed the "unlocked" half
        for the wrong reason (RELEASE_MODE), on every host.
        """
        monkeypatch.delenv("LICENSE_KEY", raising=False)
        licensing.reset_client()

        async with app.test_request_context(
            "/api/v1/license/status", headers={"Host": "portal.penguincloud.io"}
        ):
            assert licensing.current_host_is_license_exempt() is True
            assert await licensing.is_feature_entitled("sso_integration") is True

        async with app.test_request_context(
            "/api/v1/license/status", headers={"Host": "customer.example.com"}
        ):
            assert licensing.current_host_is_license_exempt() is False
            assert await licensing.is_feature_entitled("sso_integration") is False


class TestSsoStillGatesAfterTheFix:
    """SSO gated through the removed bypass, so it is the regression case."""

    @pytest.mark.asyncio
    async def test_sso_is_refused_on_an_unlicensed_domain(self, client: Any) -> None:
        """Unlicensed, non-exempt host: 403 with an upgrade path named.

        Before the fix this returned a redirect to Google (or a 500 on the
        unset client_id) because RELEASE_MODE was false in the test config —
        i.e. the gate never ran at all.
        """
        response = await client.get(
            "/api/v1/auth/oauth/google", headers={"Host": "customer.example.com"}
        )

        assert response.status_code == 403
        body = await response.get_json()
        assert body["error"] == "feature_not_entitled"
        assert body["required_tier"] == licensing.TIER_PROFESSIONAL
        assert body["current_tier"] == licensing.TIER_COMMUNITY
        assert body["feature"] == "sso_integration"

    @pytest.mark.asyncio
    async def test_sso_is_reachable_on_a_managed_domain(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The domain bypass still lets a PenguinTech deployment use SSO.

        The gate must not become unconditional in the other direction: this
        is the check that the removal did not simply break SSO everywhere.
        Asserts only that the LICENSE gate was passed — the route then fails
        on unset OAuth credentials (500), which is a separate, pre-existing
        configuration defect and is deliberately not asserted as success.
        """
        monkeypatch.delenv("LICENSE_KEY", raising=False)
        licensing.reset_client()

        response = await client.get(
            "/api/v1/auth/oauth/google", headers={"Host": "portal.penguincloud.io"}
        )

        assert response.status_code != 403
        if response.is_json:
            body = await response.get_json()
            assert (body or {}).get("error") != "feature_not_entitled"


class TestGateAndMintMeet:
    """A gate nothing mints is a permanent 403; a mint nothing gates is dead."""

    def test_every_decorated_feature_has_a_tier(self) -> None:
        """Each ``@require_feature`` name must be grantable by some tier.

        This is the guard the dead ``gough:*`` scopes needed and did not
        have: the enforce side named a string, nothing minted it, and the
        result would have been a 403 on every request with no test failing.
        """
        decorated = _decorated_feature_names()

        assert decorated, (
            "found no @require_feature decorations at all — the scanner has "
            "stopped working and this check is passing vacuously"
        )

        ungrantable = {
            feature: sites
            for feature, sites in decorated.items()
            if feature not in licensing.FEATURE_MIN_TIER
        }

        assert not ungrantable, (
            f"gated features no tier can grant: {ungrantable}. Add them to "
            f"FEATURE_MIN_TIER or the gate is a permanent 403."
        )

    def test_the_scanner_sees_the_known_gate(self) -> None:
        """A set-difference check passes vacuously on an empty left side."""
        assert "sso_integration" in _decorated_feature_names()

    @pytest.mark.parametrize(
        "feature,tier", sorted(licensing.FEATURE_MIN_TIER.items())
    )
    def test_every_minted_tier_is_a_real_tier(self, feature: str, tier: str) -> None:
        """A typo'd tier string would deny forever via ``_TIER_RANK``'s 99."""
        assert tier in licensing.TIER_ORDER, feature

    @pytest.mark.parametrize(
        "current,required,expected",
        [
            ("community", "community", True),
            ("community", "professional", False),
            ("community", "enterprise", False),
            ("professional", "community", True),
            ("professional", "professional", True),
            ("professional", "enterprise", False),
            ("enterprise", "community", True),
            ("enterprise", "professional", True),
            ("enterprise", "enterprise", True),
            # Neither side may fail open.
            ("nonsense", "community", False),
            ("enterprise", "nonsense", False),
        ],
    )
    def test_tier_matrix(self, current: str, required: str, expected: bool) -> None:
        """Tiers are cumulative upward and never permissive on an unknown."""
        assert licensing.tier_satisfies(current, required) is expected
