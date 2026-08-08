"""Gough's proxy allowlist: what the browser may and may not reach.

This is the untrusted-input path. Every case below is a path string a caller
controls, matched against the declared rules exactly as ``app/proxy.py``
matches them — so a rule that over-matches shows up here rather than in
production.

The matrix asserts DENIALS as carefully as allowances. An allowlist test that
only checks the happy paths passes just as well against ``^/`` for everything.
"""

from __future__ import annotations

import pytest

from app.adapters.base import PRODUCT_SCOPE_NAMESPACE, RouteRule, product_scope
from app.adapters.gough import GOUGH_ROUTE_ALLOWLIST, PRODUCT_TYPE, SCOPES
from app.adapters.gough.routes import _INT_ID, _UUID_ID
from app.tenancy.authz import PRODUCT_SCOPE_ACTIONS

READ = product_scope(PRODUCT_TYPE, "read")
WRITE = product_scope(PRODUCT_TYPE, "manage")


def _match(method: str, path: str) -> RouteRule | None:
    """The rule that would admit this request, or None for deny."""
    for rule in GOUGH_ROUTE_ALLOWLIST:
        if rule.matches(method, path):
            return rule
    return None


ALLOWED: list[tuple[str, str, str]] = [
    ("GET", "/healthz", READ),
    ("GET", "/api/v1/status", READ),
    ("GET", "/api/v1/nodes", READ),
    ("GET", "/api/v1/nodes/", READ),
    ("GET", "/api/v1/nodes/12", READ),
    ("GET", "/api/v1/nodes/12/tags", READ),
    ("PATCH", "/api/v1/nodes/12", WRITE),
    ("POST", "/api/v1/nodes/12/evacuate", WRITE),
    ("POST", "/api/v1/nodes/12/reject", WRITE),
    ("DELETE", "/api/v1/nodes/12", WRITE),
    ("DELETE", "/api/v1/nodes/12/biomes/5", WRITE),
    ("GET", "/api/v1/biomes", READ),
    ("GET", "/api/v1/biomes/5", READ),
    ("GET", "/api/v1/biomes/groups", READ),
    ("POST", "/api/v1/biomes/groups", WRITE),
    ("PUT", "/api/v1/biomes/5", WRITE),
    ("DELETE", "/api/v1/biomes/5", WRITE),
    ("GET", "/api/v1/biomes/deployments", READ),
    ("GET", "/api/v1/biomes/deployments/77", READ),
    ("GET", "/api/v1/biomes/deployments/77/logs", READ),
    ("GET", "/api/v1/biomes/5/upgrade-runs/9f2c1a4b-77de-4c0a-b1ef-2d3c4e5f6a7b", READ),
    ("POST", "/api/v1/biomes/deployments/77/cancel", WRITE),
    ("GET", "/api/v1/clusters/7f3a-b21c/lxd/status", READ),
    ("PATCH", "/api/v1/clusters/7f3a-b21c/config", WRITE),
    ("GET", "/api/v1/agents", READ),
    # A REAL uuid4, because that is what Gough mints for an agent id
    # (``api/agents.py``: ``agent_id = str(uuid.uuid4())``). The former
    # fixture used "aaaa-bbbb", which no Gough agent can ever have — it
    # only passed because the id pattern was a loose hex-and-hyphen run.
    ("GET", "/api/v1/agents/5c1d9e2f-4a6b-4c8d-9e0f-1a2b3c4d5e6f", READ),
    ("POST", "/api/v1/agents/5c1d9e2f-4a6b-4c8d-9e0f-1a2b3c4d5e6f/suspend", WRITE),
    ("POST", "/api/v1/agents/5c1d9e2f-4a6b-4c8d-9e0f-1a2b3c4d5e6f/resume", WRITE),
]


class TestAllowedRoutes:
    """Each supported route resolves to exactly the intended scope."""

    @pytest.mark.parametrize(("method", "path", "scope"), ALLOWED)
    def test_route_is_allowed_with_its_declared_scope(
        self, method: str, path: str, scope: str
    ) -> None:
        """The rule exists and requires the scope the design assigned it."""
        rule = _match(method, path)
        assert rule is not None, f"{method} {path} is not allowlisted"
        assert rule.required_scope == scope


DENIED: list[tuple[str, str, str]] = [
    # -- endpoints that mint or exchange credentials ----------------------
    # Proxying these would let any caller holding a portal scope drive the
    # product's own auth surface: issue an enrollment key, enrol an agent, or
    # trade the service account's session for a fresh token.
    (
        "POST",
        "/api/v1/auth/login",
        "login is the adapter's business, not a proxy route",
    ),
    ("POST", "/api/v1/auth/refresh", "token exchange must not be caller-driven"),
    ("POST", "/api/v1/agents/enrollment-keys", "mints an agent enrollment credential"),
    ("GET", "/api/v1/agents/enrollment-keys", "lists agent enrollment credentials"),
    ("POST", "/api/v1/agents/enroll", "enrols an agent against the product"),
    ("POST", "/api/v1/agents/refresh", "agent-side credential rotation"),
    ("POST", "/api/v1/agents/heartbeat", "agent-side, not operator-facing"),
    ("GET", "/api/v1/secrets", "secret material"),
    ("GET", "/api/v1/vault/status", "secret material"),
    ("GET", "/api/v1/ssh-ca/ca", "signing authority"),
    ("POST", "/api/v1/shell/exec", "remote execution"),
    # -- actions that start pollable work: TYPED route only (I5) ----------
    # Both answer 202 with ids the caller must poll. The proxy forwards a
    # response body verbatim, so proxying either hands the browser Gough's
    # raw payload with no Operation and no poll key — the UI could only
    # invalidate its queries and hope. They are served by
    # POST /products/{id}/resources/{kind}/{id}/actions/{action}, which
    # returns an ActionResult carrying the operation ids.
    (
        "POST",
        "/api/v1/nodes/12/deploy",
        "starts deployments to poll; typed action route only",
    ),
    (
        "POST",
        "/api/v1/biomes/5/upgrade",
        "starts an upgrade run to poll; typed action route only",
    ),
    # -- surfaces this integration does not cover -------------------------
    ("GET", "/api/v1/users", "portal has its own identity model"),
    ("GET", "/metrics", "scraped by the adapter, not proxied verbatim"),
    ("POST", "/api/v1/primary/replace", "cluster-primary surgery"),
    ("POST", "/api/v1/clusters/7f3a-b21c/adopt", "adopts a cluster into the fleet"),
    ("POST", "/api/v1/clusters/7f3a-b21c/lxd/join", "joins a node to the cluster"),
    ("GET", "/api/v1/clusters", "gough registers no cluster collection"),
    # -- wrong verb on an allowed path ------------------------------------
    (
        "DELETE",
        "/api/v1/agents/5c1d9e2f-4a6b-4c8d-9e0f-1a2b3c4d5e6f",
        "agents are not deletable via the portal",
    ),
    ("POST", "/api/v1/nodes/12", "no such verb"),
    ("PUT", "/api/v1/nodes/12", "nodes take PATCH"),
    ("DELETE", "/healthz", "read-only surface"),
    # -- id shapes the loose pattern used to admit (M1) -------------------
    # Each of these matched the previous "[0-9a-fA-F][0-9a-fA-F-]{0,63}"
    # agent-id run. Anchoring ID_UUID to the real 8-4-4-4-12 shape is what
    # refuses them, and a word-shaped literal Gough might mount beside its
    # agent ids in future is refused by the same property.
    ("GET", "/api/v1/agents/aaaa-bbbb", "not a uuid; loose pattern admitted it"),
    ("GET", "/api/v1/agents/dead-beef", "not a uuid; hex-shaped word"),
    ("GET", "/api/v1/agents/ad-hoc", "not a uuid; word-shaped literal"),
    ("GET", "/api/v1/agents/a", "not a uuid; single hex char"),
    # -- near-misses on an allowed prefix ---------------------------------
    ("GET", "/api/v1/nodes/12/cloud-init", "renders node credentials/config"),
    ("POST", "/api/v1/nodes/12/lxd/join", "not part of the reviewed surface"),
    ("GET", "/api/v1/nodes/12/extra/deep", "deeper than any declared rule"),
    ("GET", "/api/v2/nodes", "a future API version is not pre-approved"),
    ("GET", "/api/v1/nodesXX", "prefix must not bleed into a sibling path"),
]


class TestDeniedRoutes:
    """Deny-by-default, asserted where it matters most."""

    @pytest.mark.parametrize(("method", "path", "reason"), DENIED)
    def test_route_is_not_allowlisted(
        self, method: str, path: str, reason: str
    ) -> None:
        """No rule admits this request."""
        assert _match(method, path) is None, f"{method} {path} allowed but {reason}"


class TestTraversalAndAnchoring:
    """Structural properties, not a list of strings someone thought of."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/nodes/../../admin",
            "/api/v1/nodes/..%2fadmin",
            "/api/v1/nodes/%2e%2e/admin",
            "/api/v1/nodes\\..\\admin",
            "/api/v1/nodes//12",
            "/api/v1/nodes/12\n",
            "/api/v1/nodes/12\r\nX-Injected: 1",
        ],
    )
    def test_traversal_and_control_characters_match_nothing(self, path: str) -> None:
        """``^/api/v1/nodes/[^/]+\\Z`` alone would admit some of these.

        ``RouteRule.matches`` normalises first and a path that fails
        normalisation matches no rule, so traversal is refused rather than
        resolved — the portal never matches one string and forwards another.
        """
        assert _match("GET", path) is None

    def test_every_rule_is_fully_anchored(self) -> None:
        """Enforced at construction; asserted here so the property is visible.

        ``\\Z`` rather than ``$``: ``$`` also matches before a trailing
        newline, so ``^/healthz$`` would admit ``/healthz\\n``.
        """
        for rule in GOUGH_ROUTE_ALLOWLIST:
            assert rule.path_regex.startswith("^"), rule.path_regex
            assert rule.path_regex.endswith(r"\Z"), rule.path_regex
            assert not rule.path_regex.endswith(r"$\Z"), rule.path_regex

    def test_id_patterns_cannot_span_a_path_separator(self) -> None:
        """No id pattern may admit a slash, or one rule covers a whole subtree."""
        import re

        for pattern in (_INT_ID, _UUID_ID):
            assert re.fullmatch(pattern, "a/b") is None, pattern
        assert _match("GET", "/api/v1/nodes/12/13") is None

    def test_id_patterns_exclude_literal_sub_collection_names(self) -> None:
        """The regression behind the typed id patterns.

        ``[^/]+`` matched ``enrollment-keys`` as though it were an agent id,
        which allowlisted the route that LISTS agent enrollment credentials.
        A word-shaped literal must not be a valid id.
        """
        import re

        for literal in (
            "enrollment-keys",
            "enroll",
            "refresh",
            "heartbeat",
            "deployments",
            "groups",
        ):
            assert re.fullmatch(_INT_ID, literal) is None, literal
            assert re.fullmatch(_UUID_ID, literal) is None, literal

    def test_every_declared_scope_is_used_and_every_used_scope_declared(
        self,
    ) -> None:
        """SCOPES and the rules cannot drift apart.

        A scope in SCOPES that no rule requires is dead documentation; a scope
        on a rule that SCOPES omits escapes any audit that reads SCOPES.
        """
        used = {rule.required_scope for rule in GOUGH_ROUTE_ALLOWLIST}
        assert used == set(SCOPES)

    def test_declared_scopes_are_ones_the_portal_actually_mints(self) -> None:
        """The rules must name scopes the minter can actually produce.

        Regression guard for the brief's ``gough:{resource}:{read|write}``
        scheme: nothing mints those, so an allowlist demanding one would 403
        every token the portal can issue while looking stricter. The
        ``products:`` namespace IS minted — ``resolve_scopes`` expands the
        coarse grant across a tenant's connected product types — and
        ``test_product_scopes.py`` proves a real token carries these two.
        """
        assert set(SCOPES) == {
            f"{PRODUCT_SCOPE_NAMESPACE}:{PRODUCT_TYPE}:read",
            f"{PRODUCT_SCOPE_NAMESPACE}:{PRODUCT_TYPE}:manage",
        }
        for scope in SCOPES:
            assert scope in {
                product_scope(PRODUCT_TYPE, action) for action in PRODUCT_SCOPE_ACTIONS
            }

    def test_write_scopes_guard_every_mutating_verb(self) -> None:
        """No mutating route may be reachable with a read scope.

        The consequences are not symmetric: ``POST /nodes/{id}/deploy``
        provisions hardware and ``DELETE /nodes/{id}`` decommissions it, while
        a read is an inventory a viewer legitimately needs.
        """
        mutating = {"POST", "PUT", "PATCH", "DELETE"}
        for rule in GOUGH_ROUTE_ALLOWLIST:
            expected = WRITE if rule.method.upper() in mutating else READ
            assert rule.required_scope == expected, f"{rule.method} {rule.path_regex}"

    def test_no_rule_admits_the_product_auth_surface(self) -> None:
        """Structural version of the auth denials above.

        A future rule like ``^/api/v1/(auth|agents)/.*\\Z`` would pass every
        individual case in DENIED that nobody thought to add. This asserts the
        whole prefix, so it cannot be reopened by a broadening edit.
        """
        for path in ("/api/v1/auth", "/api/v1/auth/login", "/api/v1/auth/me"):
            for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                assert _match(method, path) is None
