"""Nest proxy allowlist: what it refuses, and that what it admits is real.

Ordered deny-first on purpose. An allowlist test that only checks happy
paths passes just as well against ``^/`` — the assertions that carry weight
are the ones naming a specific route that must NOT be reachable, and the
hazard each one represents.

The second half is the other failure mode 4G paid for: a rule can be
perfectly tight and still point at a route the product does not have, which
surfaces as an empty table rather than an error. Those tests bind every rule
against a real :class:`werkzeug.routing.Map` built from Nest's OWN source
(:mod:`tests.api.nest_route_source`), so neither the allowlist nor a fake can
be graded against the adapter's own assumptions.
"""

from __future__ import annotations

import re
from typing import Final

import pytest
from app.adapters import ADAPTER_REGISTRY
from app.adapters.base import ID_SLUG, ID_UUID, TENANT_PLACEHOLDER, RouteRule
from app.adapters.nest import NestAdapter
from app.adapters.nest.routes import (
    NEST_ROUTE_ALLOWLIST,
    NEST_UNEXPOSED_ROUTES,
    SCOPE_MANAGE,
    SCOPE_READ,
)
from nest_route_source import effective_route_table
from werkzeug.exceptions import MethodNotAllowed, NotFound
from werkzeug.routing import Map, RequestRedirect, Rule

#: A tenant id of the shape ``product_tenant_map`` supplies.
_TENANT: Final[str] = "acme-prod"

#: Concrete stand-ins for each approved id shape, used to turn a rule's
#: regex back into one path a router can be asked about.
_SAMPLE_UUID: Final[str] = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
_SAMPLE_SLUG: Final[str] = "orders-primary"


def _concrete(path_regex: str) -> str:
    """Turn one allowlist rule into a concrete path.

    Substitutes a real value for each variable shape and unescapes the
    literals, so the result is a path a caller could actually send. Raises
    if anything regex-shaped survives — a silently half-substituted path
    would be "not found" for the wrong reason and the test would report a
    routing failure that is really a bug in this helper.
    """
    body = path_regex[1:-2]  # strip ^ and \Z
    body = body.replace(re.escape(TENANT_PLACEHOLDER), _TENANT)
    body = body.replace(ID_UUID, _SAMPLE_UUID)
    body = body.replace(ID_SLUG, _SAMPLE_SLUG)
    body = body.replace("\\", "")

    leftover = set(body) & set("^$*+?[]{}()|")
    assert not leftover, (
        f"{path_regex!r} still contains regex syntax {sorted(leftover)} after "
        f"substitution — this helper does not understand the rule, so any "
        f"routing assertion made with it would be meaningless"
    )
    return body


@pytest.fixture(scope="module")
def nest_router() -> Map:
    """A real Werkzeug router built from Nest's own route registrations.

    Using Nest's source rather than a hand-written description is what makes
    this able to falsify the adapter: a fake keyed on what the adapter sends
    is correct by construction and proves nothing.

    ``effective_route_table`` parses a checkout when one exists and otherwise
    falls back to the copy vendored at ``tests/api/fixtures/nest_source.json``,
    so this **never skips**. It used to: the parser defaulted to
    ``/home/penguin/code/nest`` and nothing in ``.github/``, the Makefile or
    ``scripts/`` ever set ``$NEST_SOURCE_ROOT``, so the two checks below — the
    ones aimed squarely at the phantom-route and trailing-slash classes — ran
    on exactly one machine. ``test_nest_source_fixture.py`` keeps the vendored
    copy honest wherever a checkout does exist.
    """
    return Map(
        [
            Rule(path, endpoint=path, methods=sorted(methods))
            for path, methods in effective_route_table().items()
        ]
    )


class TestDeniedRoutes:
    """Every case here names a route that must never be proxied."""

    @pytest.mark.parametrize(("method", "path"), NEST_UNEXPOSED_ROUTES)
    def test_declared_unexposed_routes_are_refused(self, method: str, path: str) -> None:
        """The declaration is only worth having if it is enforced here too.

        ``test_adapter_registry`` asserts this registry-wide; repeating it in
        Nest's own matrix is deliberate — this is the file a Nest reviewer
        reads, and the hazard list belongs where the product knowledge is.
        """
        offenders = [rule.path_regex for rule in NEST_ROUTE_ALLOWLIST if rule.matches(method, path)]
        assert not offenders, f"{method} {path} admitted by {offenders!r}"

    @pytest.mark.parametrize(
        ("method", "path", "hazard"),
        [
            (
                "POST",
                "/api/v1/sql-files/7/execute",
                "runs operator-supplied SQL against a managed database",
            ),
            (
                "POST",
                "/api/v1/auth/login",
                "mints a Nest session from credentials",
            ),
            (
                "GET",
                "/api/v1/auth/me",
                "enumerates the identity behind the stored credential",
            ),
            (
                "GET",
                "/api/v1/license",
                "reads the licence key installed on the Nest instance",
            ),
            (
                "GET",
                "/api/v1/servers/1",
                "exposes stored database-server connection detail",
            ),
            (
                "GET",
                "/api/v1/cloud/providers/1",
                "exposes stored cloud-provider credentials",
            ),
            (
                "POST",
                "/internal/v1/operations",
                "internal control plane; forges operation records",
            ),
            (
                "GET",
                "/metrics",
                "instance-wide Prometheus data, not scoped to one tenant",
            ),
        ],
    )
    def test_named_hazards_are_refused(self, method: str, path: str, hazard: str) -> None:
        """Spelled out individually so a reviewer sees the risk, not a tuple."""
        for rule in NEST_ROUTE_ALLOWLIST:
            assert not rule.matches(
                method, path
            ), f"{method} {path} is allowlisted by {rule.path_regex!r} — {hazard}"

    @pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
    def test_no_mutating_verb_is_proxied_at_all(self, method: str) -> None:
        """Nest's allowlist is GET-only — every write is a typed method.

        Asserted as a property of the whole list rather than per route: a
        future rule added with the wrong verb fails here without anyone
        remembering to extend a matrix.
        """
        declared = {rule.method.upper() for rule in NEST_ROUTE_ALLOWLIST}
        assert method not in declared

    def test_a_tenant_rule_cannot_be_escaped_by_traversal(self) -> None:
        """Tenant scoping is a path property, so traversal is a tenant bypass.

        ``normalize_proxy_path`` refuses these before matching; this asserts
        the composed behaviour rather than trusting that it is wired in.
        """
        hazards = [
            f"/api/v1/tenants/{TENANT_PLACEHOLDER}/data-resources/../../admin",
            f"/api/v1/tenants/{TENANT_PLACEHOLDER}/data-resources/..%2fadmin",
            f"/api/v1/tenants/{TENANT_PLACEHOLDER}/data-resources/%2e%2e/admin",
            "/api/v1/tenants/other-tenant/data-resources",
        ]
        for path in hazards:
            for rule in NEST_ROUTE_ALLOWLIST:
                assert not rule.matches("GET", path), f"{path} via {rule.path_regex!r}"

    def test_an_id_slot_does_not_swallow_the_action_subpaths(self) -> None:
        """The detail rule must not admit a data-resource's action routes.

        ``/data-resources/{name}/snapshot`` is a POST-only action and is
        deliberately NOT proxied — it returns an operation the portal has to
        interpret. A detail rule that matched it would put a mutating route
        behind a read scope.
        """
        for suffix in ("snapshot", "restore", "introspect", "migrate"):
            path = f"/api/v1/tenants/{TENANT_PLACEHOLDER}/data-resources/db1/{suffix}"
            for rule in NEST_ROUTE_ALLOWLIST:
                assert not rule.matches("GET", path)
                assert not rule.matches("POST", path)

    def test_operations_slot_refuses_a_non_uuid(self) -> None:
        """Operation ids are UUIDs, so the tighter shape is the honest one."""
        for bad in ("latest", "all", "..", "1"):
            path = f"/api/v1/tenants/{TENANT_PLACEHOLDER}/operations/{bad}"
            for rule in NEST_ROUTE_ALLOWLIST:
                assert not rule.matches("GET", path)


class TestAdmittedRoutes:
    """What the allowlist does admit, and that Nest really serves it."""

    def test_the_expected_reads_are_admitted(self) -> None:
        """A short positive matrix, so a deny-everything rule fails too."""
        allowed = [
            "/health",
            "/ready",
            "/api/v1/catalog",
            f"/api/v1/tenants/{TENANT_PLACEHOLDER}/data-resources",
            f"/api/v1/tenants/{TENANT_PLACEHOLDER}/data-resources/{_SAMPLE_SLUG}",
            f"/api/v1/tenants/{TENANT_PLACEHOLDER}/operations/{_SAMPLE_UUID}",
            f"/api/v1/tenants/{TENANT_PLACEHOLDER}/snapshots",
            f"/api/v1/tenants/{TENANT_PLACEHOLDER}/protection-policies",
            f"/api/v1/tenants/{TENANT_PLACEHOLDER}/search-pools",
            f"/api/v1/tenants/{TENANT_PLACEHOLDER}/cost-report",
            f"/api/v1/tenants/{TENANT_PLACEHOLDER}/cost-report/summary",
            f"/api/v1/tenants/{TENANT_PLACEHOLDER}/anomalies",
        ]
        for path in allowed:
            assert any(
                rule.matches("GET", path) for rule in NEST_ROUTE_ALLOWLIST
            ), f"{path} should be proxied and is not"

    @pytest.mark.parametrize("rule", NEST_ROUTE_ALLOWLIST, ids=lambda r: r.path_regex)
    def test_every_rule_points_at_a_route_nest_registers(
        self, rule: RouteRule, nest_router: Map
    ) -> None:
        """A tight rule aimed at a non-existent route is still a broken screen.

        This is the check that would have caught 4G's ``/servers`` and
        ``/jobs`` — routes the committed spec advertised and the service never
        registered. It binds each rule's concrete form against Nest's real
        router, so the source of truth is Nest, not this repo.
        """
        adapter = nest_router.bind("nest.invalid")
        path = _concrete(rule.path_regex).replace(TENANT_PLACEHOLDER, _TENANT)

        try:
            adapter.match(path, method=rule.method)
        except RequestRedirect as exc:  # pragma: no cover - defensive
            pytest.fail(
                f"{rule.method} {path} redirects to {exc.new_url} — the portal "
                f"transport does not follow redirects, so this surfaces as an "
                f"empty result rather than an error"
            )
        except MethodNotAllowed:
            pytest.fail(f"nest registers {path} but not for {rule.method}")
        except NotFound:
            pytest.fail(
                f"nest registers no route matching {rule.method} {path} — the "
                f"allowlist admits a path the product does not serve"
            )

    @pytest.mark.parametrize("rule", NEST_ROUTE_ALLOWLIST, ids=lambda r: r.path_regex)
    def test_no_rule_carries_a_trailing_slash(self, rule: RouteRule) -> None:
        """Nest registers every route without one, so a slash is a 404.

        Werkzeug's ``strict_slashes`` redirects the missing-slash direction
        but not this one: a trailing slash against a no-slash registration is
        a flat 404 with no redirect back. The portal does not follow
        redirects and the proxy strips ``location``, so both directions would
        surface to a user as an empty table.
        """
        assert not rule.path_regex.endswith(r"/\Z"), rule.path_regex

    def test_nest_registers_no_route_with_a_trailing_slash(self, nest_router: Map) -> None:
        """The premise of the rule above, asserted against Nest's source.

        If Nest ever registers a ``route("/")`` collection the way Gough does,
        this fails and the adapter's path builder has to grow the same
        per-collection table Gough needed.
        """
        registered = [str(rule.rule) for rule in nest_router.iter_rules()]
        trailing = [path for path in registered if path != "/" and path.endswith("/")]
        assert not trailing, (
            f"nest now registers trailing-slash routes {trailing} — "
            f"tenant_path() emits none and would 404 against them"
        )


class TestScopes:
    """Rules name scopes the portal actually mints."""

    def test_every_rule_requires_a_mintable_product_scope(self) -> None:
        """A scope nothing mints answers 403 to every token the portal issues."""
        for rule in NEST_ROUTE_ALLOWLIST:
            assert rule.required_scope in {SCOPE_READ, SCOPE_MANAGE, "products:read"}

    def test_reads_require_the_read_scope_not_manage(self) -> None:
        """A read-only operator must reach every proxied Nest route."""
        for rule in NEST_ROUTE_ALLOWLIST:
            assert (
                rule.required_scope != SCOPE_MANAGE
            ), f"{rule.path_regex} is a GET but demands manage"

    def test_every_rule_uses_the_per_product_scope(self) -> None:
        """Per-product scopes are what allow a narrower grant later.

        Every rule — liveness included — names ``products:nest:read`` rather
        than the coarse ``products:read``. The coarse form still satisfies it
        via ``RBACEnforcer._satisfies``, so this costs nothing today and is
        what lets a principal be granted Nest and no other product later.

        The literal is asserted alongside the constant deliberately: a test
        that only compares the constant to itself passes while the constant
        is misspelt, which is the shape of the dead-scope bug 4G hit.
        """
        for rule in NEST_ROUTE_ALLOWLIST:
            assert rule.required_scope == SCOPE_READ
            assert rule.required_scope == "products:nest:read"


class TestRegistryWiring:
    """The adapter the registry hands out is the one tested here."""

    def test_registry_serves_the_integrated_nest_adapter(self) -> None:
        """Guards against the package being added but never wired in."""
        assert ADAPTER_REGISTRY["nest"] is NestAdapter
        assert NestAdapter.route_allowlist is NEST_ROUTE_ALLOWLIST
        assert NestAdapter.unexposed_routes is NEST_UNEXPOSED_ROUTES
        # The inherited default is /healthz, which Nest registers nowhere.
        assert NestAdapter.HEALTH_ENDPOINT == "/health"
