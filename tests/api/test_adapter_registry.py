"""Adapter registry: the active/planned split and its consequences.

The registry is a security boundary, not a catalogue lookup. Membership in
``ADAPTER_REGISTRY`` is what makes a product connectable and proxyable;
``PLANNED_PRODUCTS`` is metadata that must never become executable by
accident. These tests pin that separation, because the failure mode — a
planned product silently acquiring an adapter with a permissive allowlist —
would not show up as a test failure anywhere else.
"""

from typing import Any

import pytest

from app.adapters import (
    ADAPTER_REGISTRY,
    PLANNED_PRODUCTS,
    get_adapter,
    get_adapter_metadata,
    get_all_product_types,
)
from app.adapters.base import AdapterCapabilityError, AdapterContext, RouteRule


def _ctx(product: str = "gough") -> AdapterContext:
    """A minimal context; adapters are stateless so the values barely matter."""
    return AdapterContext(
        connection_id=1,
        portal_tenant_id=1,
        external_id="ext-1",
        external_kind="tenant",
        base_url="https://example.invalid",
        auth_type="bearer",
        api_key="test-key-value",
    )


class TestRegistrySplit:
    """Active products are executable; planned ones are not."""

    def test_active_registry_is_exactly_the_v2_adapters(self) -> None:
        """The active set is small and explicit — assert it by equality.

        Set equality, not `in`: a new key appearing here must be a
        deliberate edit to this test, since adding one grants a product
        type the ability to be connected and proxied.
        """
        assert set(ADAPTER_REGISTRY) == {
            "gough",
            "nest",
            "tobogganing",
            "generic",
        }

    def test_planned_products_have_no_adapter(self) -> None:
        """Every planned product refuses instantiation.

        This is the load-bearing assertion of the cleanup: the seventeen
        deleted thin adapters must not be reachable through any path.
        """
        assert PLANNED_PRODUCTS, "planned catalogue should not be empty"
        for product_type in PLANNED_PRODUCTS:
            assert product_type not in ADAPTER_REGISTRY
            with pytest.raises(ValueError):
                get_adapter(product_type, _ctx())

    def test_unknown_product_refused(self) -> None:
        """An unrecognised type raises rather than falling back to generic.

        Falling back would mean a typo'd product_type silently produced a
        working connection to the wrong integration.
        """
        with pytest.raises(ValueError):
            get_adapter("not-a-real-product", _ctx())

    def test_metadata_reports_status_for_each_tier(self) -> None:
        """Catalogue metadata distinguishes active, planned and unknown."""
        assert get_adapter_metadata("gough")["status"] == "active"
        assert get_adapter_metadata("waddleai")["status"] == "planned"
        assert get_adapter_metadata("nonsense")["status"] == "unknown"

    def test_catalogue_covers_both_tiers(self) -> None:
        """get_all_product_types lists actives and planned together."""
        catalogue = get_all_product_types()
        by_type = {entry["product_type"]: entry for entry in catalogue}

        assert len(catalogue) == len(ADAPTER_REGISTRY) + len(PLANNED_PRODUCTS)
        for product_type in ADAPTER_REGISTRY:
            assert by_type[product_type]["status"] == "active"
        for product_type in PLANNED_PRODUCTS:
            assert by_type[product_type]["status"] == "planned"


class TestAllowlists:
    """Route allowlists are declarative and closed by default."""

    def test_every_active_adapter_declares_an_allowlist(self) -> None:
        """A missing attribute would make the proxy raise, not deny."""
        for product_type, adapter_class in ADAPTER_REGISTRY.items():
            rules = getattr(adapter_class, "route_allowlist", None)
            assert isinstance(rules, list), product_type
            for rule in rules:
                assert isinstance(rule, RouteRule)
                assert rule.required_scope, f"{product_type}: rule without a scope"

    def test_generic_adapter_proxies_nothing(self) -> None:
        """The unknown-product fallback must not relay anything.

        A generic adapter cannot know which of an unknown product's routes
        are safe or what scope each needs, so an empty allowlist is the only
        defensible default — anything else is an open relay to an operator-
        supplied URL with a stored credential attached.
        """
        assert ADAPTER_REGISTRY["generic"].route_allowlist == []

    def test_stub_adapters_expose_only_read_only_liveness(self) -> None:
        """Products with no Phase-4 integration allow liveness and nothing more.

        Gough is deliberately absent: Phase 4G gave it a real allowlist with
        write rules. Its matrix lives in ``test_gough_allowlist.py``, which
        asserts both what it admits and what it must not.
        """
        for product_type in ("nest", "tobogganing"):
            rules = ADAPTER_REGISTRY[product_type].route_allowlist
            assert {rule.method for rule in rules} == {"GET"}
            assert {rule.required_scope for rule in rules} == {"products:read"}

    def test_only_integrated_products_may_proxy_a_mutating_verb(self) -> None:
        """Write access is a per-integration decision, never a default.

        Structural guard on the registry as a whole: a product picks up a
        mutating proxy rule only by being integrated and reviewed. Nest and
        Tobogganing land next, and this fails the moment one of them ships a
        write rule without its own allowlist matrix.
        """
        integrated = {"gough"}
        for product_type, adapter_class in ADAPTER_REGISTRY.items():
            methods = {rule.method.upper() for rule in adapter_class.route_allowlist}
            mutating = methods - {"GET", "HEAD", "OPTIONS"}
            if product_type not in integrated:
                assert not mutating, f"{product_type} proxies {sorted(mutating)}"

    def test_route_rule_matching_is_anchored_and_method_exact(self) -> None:
        """A rule matches its own method and path shape, and nothing near it."""
        rule = RouteRule("GET", r"^/health(z)?\Z", "products:read")

        assert rule.matches("GET", "/health") is True
        assert rule.matches("GET", "/healthz") is True
        assert (
            rule.matches("get", "/healthz") is True
        ), "method compare is case-insensitive"
        assert rule.matches("POST", "/healthz") is False
        # Anchoring: a path that merely starts with the pattern must not match.
        assert rule.matches("GET", "/healthz/../admin") is False
        assert rule.matches("GET", "/nothealthz") is False


@pytest.mark.asyncio
class TestHealthOnlyBehaviour:
    """Unimplemented operations raise rather than returning empty results."""

    @pytest.mark.parametrize("product_type", ["nest", "tobogganing", "generic"])
    async def test_capabilities_reports_health_only(self, product_type: str) -> None:
        """capabilities() tells the truth about what is implemented.

        Gough is excluded because 4G implemented it; ``capabilities()`` must
        now list what it really does, and that list is asserted in
        ``test_gough_adapter.py``.
        """
        adapter = get_adapter(product_type, _ctx())
        assert await adapter.capabilities(_ctx()) == ["health"]

    async def test_gough_reports_the_operations_it_implements(self) -> None:
        """An integrated product must not still claim health-only.

        capabilities() drives what the UI offers, so a stale answer here hides
        working features rather than breaking loudly.
        """
        adapter = get_adapter("gough", _ctx())
        reported = await adapter.capabilities(_ctx())
        assert "health" in reported
        assert {"list_resources", "get_operation", "cancel_operation"} <= set(reported)

    @pytest.mark.parametrize("product_type", ["nest", "tobogganing", "generic"])
    async def test_resource_operations_raise_capability_error(
        self, product_type: str
    ) -> None:
        """Every resource op raises AdapterCapabilityError (rendered 501).

        Deliberately not an empty Page: a caller cannot distinguish "this
        product has no resources" from "the portal cannot list them yet",
        and the first reading ships a dashboard reporting zero of
        everything.
        """
        adapter = get_adapter(product_type, _ctx())
        ctx = _ctx()

        with pytest.raises(AdapterCapabilityError):
            await adapter.list_resources("vm", ctx)
        with pytest.raises(AdapterCapabilityError):
            await adapter.get_resource("vm", "1", ctx)
        with pytest.raises(AdapterCapabilityError):
            await adapter.create_resource("vm", {}, ctx)
        with pytest.raises(AdapterCapabilityError):
            await adapter.update_resource("vm", "1", {}, ctx)
        with pytest.raises(AdapterCapabilityError):
            await adapter.delete_resource("vm", "1", ctx)
        with pytest.raises(AdapterCapabilityError):
            await adapter.metrics_summary(ctx)
        with pytest.raises(AdapterCapabilityError):
            await adapter.list_users(ctx)
        with pytest.raises(AdapterCapabilityError):
            await adapter.invite_user({}, ctx)

    async def test_capability_error_names_the_product(self) -> None:
        """The 501 message identifies which product could not do what.

        Uses nest now that gough implements ``metrics_summary`` — the property
        under test is the message, not which product happens to lack the op.
        """
        adapter = get_adapter("nest", _ctx())
        with pytest.raises(AdapterCapabilityError) as excinfo:
            await adapter.metrics_summary(_ctx())
        assert "nest" in str(excinfo.value)
        assert "metrics_summary" in str(excinfo.value)


class TestNoSyncHttpClient:
    """The portal has one HTTP client, and it is async."""

    def test_app_package_never_imports_requests(self) -> None:
        """`requests` is blocking; this service is async end to end.

        Asserted against the source tree rather than by import, because the
        damage from a sync call is a stalled event loop under load — not an
        error any functional test would surface.
        """
        import pathlib

        app_dir = pathlib.Path(__file__).resolve().parents[2] / (
            "services/portal-api/app"
        )
        offenders = [
            str(path.relative_to(app_dir))
            for path in app_dir.rglob("*.py")
            if any(
                line.startswith(("import requests", "from requests"))
                for line in path.read_text().splitlines()
            )
        ]
        assert offenders == [], f"blocking `requests` import in: {offenders}"


class TestDiscoveryProfilesDecoupled:
    """Discovery fingerprints live outside the adapter contract."""

    def test_profiles_cover_only_products_with_adapters(self) -> None:
        """Discovering a product the portal cannot manage helps nobody.

        It would offer the operator a connection that fails at the first
        proxied call, so profiles are restricted to the active tier.
        """
        from app.adapters.discovery_profiles import DISCOVERY_PROFILES

        for product_type in DISCOVERY_PROFILES:
            assert product_type in ADAPTER_REGISTRY
            assert product_type not in PLANNED_PRODUCTS

    def test_profiles_declare_ports_and_signatures(self) -> None:
        """A profile with no ports would silently never be probed."""
        from app.adapters.discovery_profiles import DISCOVERY_PROFILES

        assert DISCOVERY_PROFILES, "discovery has nothing to look for"
        for product_type, profile in DISCOVERY_PROFILES.items():
            assert profile.product_type == product_type
            assert profile.ports, f"{product_type}: no ports to probe"
            assert profile.signatures, f"{product_type}: no way to confirm a match"
            assert profile.health_endpoint.startswith("/")

    def test_profile_is_immutable(self) -> None:
        """Frozen: a probe loop must not be able to mutate shared config."""
        import dataclasses

        from app.adapters.discovery_profiles import DISCOVERY_PROFILES

        profile = DISCOVERY_PROFILES["gough"]
        with pytest.raises(dataclasses.FrozenInstanceError):
            profile.product_type = "nest"  # type: ignore[misc]


def test_adapter_context_is_frozen_and_slotted() -> None:
    """Context cannot be mutated mid-call, and carries no __dict__.

    Frozen matters for correctness (an adapter cannot rewrite the tenant or
    credential it was handed); slots matters because these are built per
    request on a hot path.
    """
    import dataclasses

    ctx = _ctx()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.api_key = "swapped"  # type: ignore[misc]
    assert not hasattr(ctx, "__dict__")


def test_route_rule_is_frozen_and_slotted() -> None:
    """Allowlist rules are shared class-level state — they must be immutable."""
    import dataclasses

    rule = RouteRule("GET", r"^/x\Z", "products:read")
    with pytest.raises(dataclasses.FrozenInstanceError):
        rule.required_scope = "products:manage"  # type: ignore[misc]
    assert not hasattr(rule, "__dict__")


def test_get_adapter_returns_a_fresh_instance(_unused: Any = None) -> None:
    """No shared adapter instance between callers.

    Adapters are stateless and take ctx per method, but returning a
    singleton would make any future instance attribute a cross-tenant
    leak waiting to happen.
    """
    first = get_adapter("gough", _ctx())
    second = get_adapter("gough", _ctx())
    assert first is not second
