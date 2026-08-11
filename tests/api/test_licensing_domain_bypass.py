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
from app import licensing, quotas
from app.license import LicenseManager
from quart import Quart

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


#: Every call whose first positional argument names a licensed feature and
#: whose effect is to refuse when the licence does not grant it. Decorators
#: are only one of the shapes — the capability gates on tenant creation and
#: delegated-admin enrolment are inline calls, and a scanner that only knew
#: about ``@require_feature`` would report them as unenforced.
_ENFORCEMENT_CALLS: Final[frozenset[str]] = frozenset(
    {
        "require_feature",
        "_capability_refusal",
        "is_feature_entitled",
        "is_feature_entitled_blocking",
        "is_feature_available",
        "product_gate_refusal",
    }
)


def _gated_feature_names() -> set[str]:
    """Every feature name enforced somewhere in the app package.

    Parsed with ``ast`` rather than regex so a call spanning lines, or one
    reached through a module prefix (``licensing.is_feature_entitled``), is
    still seen. Source inspection proves a name is *spelled* at a gate, not
    that the gate works — the behavioural tests for each gate are what prove
    that, and this exists to catch the features that have no gate at all.
    """
    names: set[str] = set()
    for path in sorted(_APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            called = (
                func.attr
                if isinstance(func, ast.Attribute)
                else func.id
                if isinstance(func, ast.Name)
                else ""
            )
            if called not in _ENFORCEMENT_CALLS:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                names.add(first.value)
    return names


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
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name in (
                "is_feature_enabled",
                "is_feature_entitled",
            ):
                statements = list(node.body)
                if ast.get_docstring(node) is not None:
                    statements = statements[1:]
                bodies.extend(statements)

        assert bodies, "neither entitlement method was found — parser is stale"

        for statement in bodies:
            referenced = {
                child.attr for child in ast.walk(statement) if isinstance(child, ast.Attribute)
            } | {child.id for child in ast.walk(statement) if isinstance(child, ast.Name)}
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
        """Managed domains are exempt."""
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
    async def test_the_answer_does_not_depend_on_being_in_a_request(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Configuration answers identically in and out of a request.

        It used to answer only inside one (and fail closed outside), which
        meant the bypass was a property of the caller rather than of the
        deployment. Background work now inherits the same, auditable answer.
        """
        monkeypatch.delenv("SERVER_NAME", raising=False)
        monkeypatch.setenv("BASE_URL", "https://portal.penguincloud.io")

        assert licensing.current_host_is_license_exempt() is True
        async with app.test_request_context("/api/v1/license/status"):
            assert licensing.current_host_is_license_exempt() is True

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
        monkeypatch.delenv("SERVER_NAME", raising=False)
        licensing.reset_client()

        monkeypatch.setenv("BASE_URL", "https://portal.penguincloud.io")
        assert licensing.current_host_is_license_exempt() is True
        assert await licensing.is_feature_entitled("sso_integration") is True

        monkeypatch.setenv("BASE_URL", "https://customer.example.com")
        assert licensing.current_host_is_license_exempt() is False
        assert await licensing.is_feature_entitled("sso_integration") is False

    @pytest.mark.asyncio
    async def test_a_spoofed_host_header_cannot_take_the_bypass(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``curl -H 'Host: x.penguincloud.io'`` must not disable the paywall.

        This is the whole licensing threat model in one request. The bypass
        used to read ``request.host``, so on any self-hosted deployment a
        single header entitled every licensed feature, passed every tier
        gate and resolved the Enterprise limits table — and the operator
        sending it is precisely the party the licence constrains, with full
        control of their own ingress and direct access to the pod.
        """
        monkeypatch.delenv("LICENSE_KEY", raising=False)
        monkeypatch.delenv("SERVER_NAME", raising=False)
        monkeypatch.setenv("BASE_URL", "https://portal.customer.example.com")
        licensing.reset_client()

        for spoof in (
            "portal.penguincloud.io",
            "anything.penguintech.cloud",
            "x.localhost.local",
        ):
            async with app.test_request_context("/api/v1/license/status", headers={"Host": spoof}):
                assert licensing.configured_host() == "portal.customer.example.com"
                assert licensing.current_host_is_license_exempt() is False
                assert await licensing.is_feature_entitled("sso_integration") is False
                limits = await quotas.resolve_limits()
                assert limits == quotas.DEFAULT_TIER_LIMITS[licensing.TIER_COMMUNITY]

    @pytest.mark.asyncio
    async def test_an_unconfigured_deployment_is_not_exempt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No configured host fails closed rather than open."""
        monkeypatch.delenv("BASE_URL", raising=False)
        monkeypatch.delenv("SERVER_NAME", raising=False)
        assert licensing.configured_host() == ""
        assert licensing.current_host_is_license_exempt() is False

    @pytest.mark.parametrize(
        "configured,expected",
        [
            ("https://portal.penguincloud.io/path", "portal.penguincloud.io"),
            ("portal.penguincloud.io:8443", "portal.penguincloud.io"),
            ("PORTAL.PenguinCloud.IO", "portal.penguincloud.io"),
            ("//portal.penguincloud.io", "portal.penguincloud.io"),
            ("", ""),
        ],
    )
    def test_configured_host_is_reduced_to_a_bare_host(
        self, configured: str, expected: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Configured host is reduced to a bare host."""
        monkeypatch.delenv("SERVER_NAME", raising=False)
        if configured:
            monkeypatch.setenv("BASE_URL", configured)
        else:
            monkeypatch.delenv("BASE_URL", raising=False)
        assert licensing.configured_host() == expected


class TestSsoStillGatesAfterTheFix:
    """SSO gated through the removed bypass, so it is the regression case."""

    @pytest.mark.asyncio
    async def test_sso_is_refused_on_an_unlicensed_domain(self, client: Any) -> None:
        """Unlicensed, non-exempt host: 403 with an upgrade path named.

        Before the fix this returned a redirect to Google (or a 500 on the
        unset client_id) because RELEASE_MODE was false in the test config —
        i.e. the gate never ran at all.
        """
        response = await client.get("/api/v1/auth/oauth/google")

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
        monkeypatch.delenv("SERVER_NAME", raising=False)
        monkeypatch.setenv("BASE_URL", "https://portal.penguincloud.io")
        licensing.reset_client()

        response = await client.get("/api/v1/auth/oauth/google")

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

    def test_every_declared_feature_is_gated_or_declared_unbuilt(self) -> None:
        """THE CONVERSE, which is where the real gap was.

        The check above catches a gate naming a feature nobody mints. This
        one catches the opposite and far quieter failure: a feature declared
        in ``FEATURE_MIN_TIER`` — i.e. sold — that nothing anywhere checks.
        Eight of the nine entries were in that state, including two whose
        capability is fully built (``delegated_admin``, ``multi_tenant``),
        so the licence said "Enterprise" while the code said "help
        yourself".

        A feature is acceptable in exactly two states: gated at a real call
        site, or listed in ``NOT_YET_IMPLEMENTED`` because the capability
        does not exist to gate. Anything else fails here, so the last step
        of building one of these is removing it from that set — and adding a
        new licensed feature without a gate fails immediately.
        """
        enforced = set(_gated_feature_names())

        assert enforced, (
            "found no feature enforcement sites at all — the scanner has "
            "stopped working and this check is passing vacuously"
        )

        unenforced = {
            feature
            for feature in licensing.FEATURE_MIN_TIER
            if feature not in enforced and feature not in licensing.NOT_YET_IMPLEMENTED
        }

        assert not unenforced, (
            f"licensed features nothing enforces: {sorted(unenforced)}. Gate "
            f"them at a call site, or add them to NOT_YET_IMPLEMENTED with "
            f"the reason they cannot be gated yet."
        )

    def test_not_yet_implemented_names_are_real_features(self) -> None:
        """The escape hatch cannot excuse a name the contract does not have."""
        unknown = licensing.NOT_YET_IMPLEMENTED - set(licensing.FEATURE_MIN_TIER)
        assert not unknown, f"NOT_YET_IMPLEMENTED names no tier grants: {unknown}"

    def test_a_built_feature_may_not_hide_in_not_yet_implemented(self) -> None:
        """Listing an enforced feature as unbuilt would re-open the hole."""
        both = licensing.NOT_YET_IMPLEMENTED & set(_gated_feature_names())
        assert not both, (
            f"features listed as unbuilt but actually gated: {sorted(both)}. "
            f"Remove them from NOT_YET_IMPLEMENTED."
        )

    @pytest.mark.parametrize("feature,tier", sorted(licensing.FEATURE_MIN_TIER.items()))
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
