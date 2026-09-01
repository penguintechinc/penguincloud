"""Adapter registry: the active/planned split and its consequences.

The registry is a security boundary, not a catalogue lookup. Membership in
``ADAPTER_REGISTRY`` is what makes a product connectable and proxyable;
``PLANNED_PRODUCTS`` is metadata that must never become executable by
accident. These tests pin that separation, because the failure mode — a
planned product silently acquiring an adapter with a permissive allowlist —
would not show up as a test failure anywhere else.
"""

import re
from typing import Any

import pytest
from app.adapters import (
    ADAPTER_REGISTRY,
    PLANNED_PRODUCTS,
    get_adapter,
    get_adapter_metadata,
    get_all_product_types,
)
from app.adapters.base import (
    APPROVED_ID_PATTERNS,
    ID_INT,
    ID_SLUG,
    ID_UUID,
    TENANT_PLACEHOLDER_PATTERN,
    AdapterCapabilityError,
    AdapterContext,
    RouteRule,
)


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
            "waddleai",
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
        assert get_adapter_metadata("waddleai")["status"] == "active"
        assert get_adapter_metadata("marchproxy")["status"] == "planned"
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

        Gough, Nest and Tobogganing are deliberately absent: 4G, 4N and 4T gave
        each a real allowlist. Their matrices live in ``test_gough_allowlist.py``,
        ``test_nest_allowlist.py`` and ``test_tobogganing_allowlist.py``, which
        assert both what each admits and what it must not.

        ``generic`` is the only remaining stub, and its allowlist is EMPTY
        rather than liveness-only — it exists so an operator can register and
        monitor an endpoint the portal has no integration for, without that
        endpoint becoming proxyable at all.
        """
        rules = ADAPTER_REGISTRY["generic"].route_allowlist
        assert rules == [], (
            "the generic adapter must proxy nothing — it is the fallback for "
            "products the portal has no integration for"
        )

    def test_only_integrated_products_may_proxy_a_mutating_verb(self) -> None:
        """Write access is a per-integration decision, never a default.

        Structural guard on the registry as a whole: a product picks up a
        mutating proxy rule only by being integrated and reviewed. Each entry
        below has its own allowlist matrix asserting what it admits and what it
        refuses; this fails the moment a product ships a write rule without one.

        Nest is NOT listed despite being integrated: every Nest write answers
        202 with an operation, so all of them are typed methods and its
        allowlist stays GET-only. Tobogganing is listed because its
        user-reachable mutations are all synchronous (no 202 anywhere on that
        surface), which is what makes proxying them legitimate — see
        ``app/adapters/tobogganing/routes.py``.
        """
        integrated = {"gough", "tobogganing"}
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
        assert rule.matches("get", "/healthz") is True, "method compare is case-insensitive"
        assert rule.matches("POST", "/healthz") is False
        # Anchoring: a path that merely starts with the pattern must not match.
        assert rule.matches("GET", "/healthz/../admin") is False
        assert rule.matches("GET", "/nothealthz") is False


@pytest.mark.asyncio
class TestHealthOnlyBehaviour:
    """Unimplemented operations raise rather than returning empty results."""

    @pytest.mark.parametrize("product_type", ["generic"])
    async def test_capabilities_reports_health_only(self, product_type: str) -> None:
        """capabilities() tells the truth about what is implemented.

        Gough and Nest are excluded because 4G and 4N implemented them;
        ``capabilities()`` must now list what each really does, asserted in
        ``test_gough_adapter.py`` and ``test_nest_adapter.py``.
        """
        adapter = get_adapter(product_type, _ctx())
        assert await adapter.capabilities(_ctx()) == ["health"]

    async def test_nest_reports_the_operations_it_implements(self) -> None:
        """An integrated product must not still claim health-only.

        capabilities() drives what the UI offers, so a stale answer here
        hides working features rather than breaking loudly. Nest's cancel and
        log operations are deliberately absent — it publishes neither — and
        asserting that keeps a future edit from advertising them.
        """
        adapter = get_adapter("nest", _ctx())
        reported = await adapter.capabilities(_ctx())
        assert "health" in reported
        assert {
            "list_resources",
            "create_resource",
            "perform_action",
            "get_operation",
        } <= set(reported)
        assert "cancel_operation" not in reported
        assert "operation_logs" not in reported

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
    async def test_resource_operations_raise_capability_error(self, product_type: str) -> None:
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

        app_dir = pathlib.Path(__file__).resolve().parents[2] / ("services/portal-api/app")
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


# -- typed id patterns, enforced across every registered adapter ----------


def _rule_segments(rule: RouteRule) -> list[str]:
    r"""Split a ``path_regex`` into its path segments.

    Strips the mandatory ``^`` / ``\\Z`` anchors and the optional trailing
    ``/?`` some collection rules carry, then splits on the ``/`` characters
    that genuinely separate segments.

    Character-class aware, and that is not decorative: ``[^/]+`` — the exact
    pattern this whole check exists to refuse — contains a ``/`` INSIDE a
    character class. A naive ``body.split("/")`` tears it into ``['[^', ']+']``
    and reports two nonsense segments, so the one input the checker must
    describe correctly is the one it got wrong. Backslash escapes are honoured
    for the same reason (``\\/`` is a literal slash, not a separator).
    """
    body = rule.path_regex
    assert body.startswith("^") and body.endswith(r"\Z")
    body = body[1:-2]
    if body.endswith("/?"):
        body = body[:-2]

    segments: list[str] = []
    current: list[str] = []
    in_class = False
    escaped = False

    for char in body:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            current.append(char)
            escaped = True
            continue
        if char == "[":
            in_class = True
        elif char == "]":
            in_class = False
        if char == "/" and not in_class:
            if current:
                segments.append("".join(current))
            current = []
            continue
        current.append(char)

    if current:
        segments.append("".join(current))
    return segments


#: A segment made only of these characters is a literal path component, not a
#: pattern. Anything containing regex metacharacters is treated as an id slot.
_LITERAL_SEGMENT = re.compile(r"^[A-Za-z0-9_-]+\Z")


def _is_literal(segment: str) -> bool:
    r"""True when a segment is a plain path literal.

    The escaped tenant placeholder counts as a literal, by EXACT equality
    with the contract's own constant and nothing looser.

    It reads as a pattern only because braces are regex metacharacters, but
    ``re.escape("{tenant}")`` matches exactly one string — the seven-plus-two
    characters ``{tenant}`` — and matches no other segment a caller could
    send. It is a constant token the caller writes verbatim and the proxy
    substitutes AFTER matching (``app/proxy.py``: allowlist at :444,
    substitution at :482), which is why a tenant-addressed rule must contain
    it at all.

    Treating it as an id slot instead would demand it be added to
    ``APPROVED_ID_PATTERNS`` — declaring a fixed literal to be an approved
    *id shape*, which would then be accepted anywhere an id is expected. That
    is strictly worse than naming it here for what it is.

    Exact equality is what keeps this from being a loophole: ``\\{tenant\\}x``,
    ``\\{tenant\\}|.*`` and a hand-escaped near-miss are all still patterns and
    must still be approved id shapes. ``test_tenant_placeholder_exemption_is_
    exact`` pins that.
    """
    if segment == TENANT_PLACEHOLDER_PATTERN:
        return True
    return _LITERAL_SEGMENT.match(segment) is not None


def _adapters_with_rules() -> list[tuple[str, list[RouteRule]]]:
    """Every registered adapter that declares at least one route rule."""
    return [
        (product_type, list(adapter_cls.route_allowlist))
        for product_type, adapter_cls in ADAPTER_REGISTRY.items()
        if getattr(adapter_cls, "route_allowlist", None)
    ]


class TestTypedIdPatterns:
    r"""No id slot may swallow a literal sibling route.

    This is the registry-wide form of the defect that shipped twice in Task
    4G. A permissive id pattern is correctly anchored, reads as correct, and
    silently allowlists whatever literal sub-collection the product mounts at
    the same depth:

        ``^/api/v1/agents/[^/]+\\Z``  also admits  ``/api/v1/agents/enrollment-keys``

    — the route that lists agent enrollment credentials.

    The check lives here rather than in a per-adapter test file on purpose:
    a Phase-4 adapter inherits it by being added to ``ADAPTER_REGISTRY``, so
    Nest and Tobogganing cannot repeat this by simply not writing the test.

    Scope and limits. This compares an id slot against literals THIS ADAPTER
    ALLOWLISTS at the same depth beneath the same prefix. It cannot see a
    literal the product registers but the adapter does not allowlist —
    ``enrollment-keys`` is exactly that case — because nothing in the portal
    knows the product's full route table. That case is covered per-adapter by
    a deny matrix naming the hazard (``test_gough_allowlist.py``), and both
    layers are needed: this one generalises, that one knows the product.
    """

    def test_segment_split_matches_rule_text(self) -> None:
        """The splitter must be lossless, or every assertion below is soft."""
        for _product_type, rules in _adapters_with_rules():
            for rule in rules:
                rebuilt = "/" + "/".join(_rule_segments(rule))
                stripped = rule.path_regex[1:-2]
                assert stripped.rstrip("/?") == rebuilt.rstrip("/?") or (
                    stripped == rebuilt
                ), f"segment split lost information for {rule.path_regex!r}"

    @pytest.mark.parametrize("product_type", sorted(p for p, _ in _adapters_with_rules()))
    def test_no_id_pattern_matches_a_sibling_literal(self, product_type: str) -> None:
        """An id slot must not match a literal route at the same position.

        "Same position" means: another rule in the SAME adapter whose leading
        segments are identical and which carries a literal where this rule
        carries a pattern. That is precisely the shape of the two real
        defects — ``/agents/{id}`` vs ``/agents/enrollment-keys``, and
        ``/biomes/{id}`` vs ``/biomes/deployments``.
        """
        rules = dict(_adapters_with_rules())[product_type]
        parsed = [(rule, _rule_segments(rule)) for rule in rules]

        for rule, segments in parsed:
            for index, segment in enumerate(segments):
                if _is_literal(segment):
                    continue
                prefix = segments[:index]
                compiled = re.compile(segment)
                for other_rule, other_segments in parsed:
                    if len(other_segments) <= index:
                        continue
                    if other_segments[:index] != prefix:
                        continue
                    sibling = other_segments[index]
                    if not _is_literal(sibling):
                        continue
                    assert compiled.fullmatch(sibling) is None, (
                        f"{product_type}: id pattern {segment!r} in "
                        f"{rule.path_regex!r} also matches the literal "
                        f"{sibling!r} from {other_rule.path_regex!r} — that "
                        f"literal route is allowlisted under the id rule's "
                        f"scope, not its own"
                    )

    @pytest.mark.parametrize("product_type", sorted(p for p, _ in _adapters_with_rules()))
    def test_every_variable_segment_is_an_approved_id_shape(self, product_type: str) -> None:
        r"""POSITIVE check: a variable segment must BE an approved id shape.

        This replaces a blocklist of ``("[^/]+", "[^/]*", ".+", ".*")`` matched
        as substrings against the whole ``path_regex``. That check was
        evadable and therefore gave 4N/4T documentation rather than
        enforcement: ``\\w+``, ``[^/]{1,64}``, ``[A-Za-z0-9_-]+`` and ``\\S+``
        all pass it, and every one of them re-admits the word-shaped literals
        (``enroll``, ``refresh``, ``groups``, ``login``) that are the exact
        class which allowlisted ``/api/v1/agents/enrollment-keys``.

        A blocklist can only refuse the spellings someone thought of. This
        refuses everything that is not deliberately approved, whatever it is
        spelled as — adding a shape means editing
        :data:`~app.adapters.base.APPROVED_ID_PATTERNS`, which is a reviewed
        contract change rather than a regex invented in an adapter module.

        Segments are parsed and compared individually, not substring-matched:
        a check against the whole string cannot tell which part of a rule the
        offending text belongs to.
        """
        for rule in dict(_adapters_with_rules())[product_type]:
            for segment in _rule_segments(rule):
                if _is_literal(segment):
                    continue
                assert segment in APPROVED_ID_PATTERNS, (
                    f"{product_type}: segment {segment!r} in "
                    f"{rule.path_regex!r} is neither a plain literal nor an "
                    f"approved id shape. Use ID_INT / ID_UUID / ID_SLUG from "
                    f"app.adapters.base, or add a new shared constant to "
                    f"APPROVED_ID_PATTERNS deliberately."
                )

    @pytest.mark.parametrize(
        "evasion",
        [
            r"\w+",
            r"[^/]{1,64}",
            r"[A-Za-z0-9_-]+",
            r"\S+",
            r"[^/]+",
            r".+",
            r"[a-z]+",
            r".{1,32}",
        ],
    )
    def test_the_check_rejects_the_evasions_that_motivated_it(self, evasion: str) -> None:
        """Each of these passed the old substring blocklist. None may pass now.

        The first four are the specific evasions named in review. They are not
        theoretical: every one matches ``enroll``, ``refresh`` and ``groups``,
        so any of them in an agent-id slot re-opens the enrollment-keys hole.
        """
        rule = RouteRule("GET", rf"^/api/v1/agents/{evasion}\Z", "products:read")
        segments = _rule_segments(rule)
        variable = [seg for seg in segments if not _is_literal(seg)]

        assert variable == [evasion], "the evasion must be seen as one segment"
        assert evasion not in APPROVED_ID_PATTERNS, (
            f"{evasion!r} must not be an approved id shape — it matches "
            f"word-shaped literals such as 'enroll' and 'groups'"
        )
        # And it really does admit the hazardous literals, which is why.
        assert re.fullmatch(evasion, "enroll") is not None

    def test_tenant_placeholder_counts_as_a_literal_segment(self) -> None:
        """4N: a tenant-addressed rule must carry the placeholder verbatim.

        Nest addresses every resource under ``/tenants/{tenant}/...`` and the
        proxy matches the allowlist BEFORE substituting, so the rule contains
        the escaped placeholder. It matches exactly one string and is a
        constant, not an id slot — see :func:`_is_literal`.
        """
        assert _is_literal(TENANT_PLACEHOLDER_PATTERN)
        assert TENANT_PLACEHOLDER_PATTERN not in APPROVED_ID_PATTERNS, (
            "the placeholder must be a literal, never an approved id shape — "
            "an approved shape is accepted in every id slot in every adapter"
        )

    @pytest.mark.parametrize(
        "near_miss",
        [
            r"\{tenant\}x",
            r"\{tenant\}|.*",
            r"\{tenant\}?",
            r"\{tenants\}",
            r"\{[a-z]+\}",
            r"x\{tenant\}",
        ],
    )
    def test_tenant_placeholder_exemption_is_exact(self, near_miss: str) -> None:
        r"""The exemption is equality, not a prefix or a family of shapes.

        Written as the falsification of the exemption added in 4N: a
        substring or ``startswith`` test would admit every entry here, and
        ``\\{tenant\\}|.*`` in particular would allowlist the entire path
        space beneath a rule that reads as tenant-scoped.
        """
        assert not _is_literal(near_miss), (
            f"{near_miss!r} is not the tenant placeholder and must still be " f"judged as a pattern"
        )
        assert (
            near_miss not in APPROVED_ID_PATTERNS
        ), f"{near_miss!r} must not be an approved id shape"

    def test_approved_shapes_are_exactly_the_shared_constants(self) -> None:
        """The approved set is small and explicit — assert it by equality.

        Set equality, not membership: widening it must be a deliberate edit to
        this test, because every entry is a shape every adapter may then use.
        """
        assert APPROVED_ID_PATTERNS == frozenset({ID_INT, ID_UUID, ID_SLUG})

    def test_shared_id_constants_reject_word_shaped_literals(self) -> None:
        """The constants themselves must hold the property they promise."""
        hazards = [
            "enrollment-keys",
            "enroll",
            "refresh",
            "heartbeat",
            "deployments",
            "groups",
            "login",
            "admin",
        ]
        for literal in hazards:
            assert re.fullmatch(ID_INT, literal) is None, literal
            assert re.fullmatch(ID_UUID, literal) is None, literal

    def test_id_uuid_matches_a_real_uuid_and_nothing_looser(self) -> None:
        """M1: anchored to 8-4-4-4-12, not a loose hex-and-hyphen run."""
        assert re.fullmatch(ID_UUID, "9f2c1a4b-77de-4c0a-b1ef-2d3c4e5f6a7b")
        # The loose form this replaced matched all of these.
        for near_miss in ("aaaa-bbbb", "dead-beef", "a", "ad-hoc", "7f3a-b21c"):
            assert re.fullmatch(ID_UUID, near_miss) is None, near_miss

    def test_id_slug_is_bounded_and_excludes_separators(self) -> None:
        """ID_SLUG is the loosest constant, so its limits are the contract.

        It must never admit a path separator, a traversal, or an unbounded
        run — those are the properties that keep it a *typed* id rather than
        ``[^/]+`` under a friendlier name.
        """
        assert re.fullmatch(ID_SLUG, "dep-77")
        assert re.fullmatch(ID_SLUG, "7f3a-b21c")
        for rejected in ("..", "a/b", "a\\b", "", "-leading", "a" * 200):
            assert re.fullmatch(ID_SLUG, rejected) is None, rejected


class TestUnexposedRoutes:
    """Declared product routes the proxy must refuse.

    The id checks above are structurally blind to this class. They compare an
    id pattern against the literals an adapter DECLARES, so a route the
    product mounts and the adapter deliberately omits cannot be seen by them —
    and ``GET /api/v1/agents/enrollment-keys`` is exactly that route. It was
    admitted by a loose agent-id pattern, and no amount of analysing the
    allowlist in isolation would have found it, because the allowlist never
    mentioned it.

    Nothing in the portal can enumerate a product's route table, so the gap
    cannot be closed by inference. It is closed by declaration:
    ``Adapter.unexposed_routes`` names concrete requests that must be refused,
    and these tests hold every registered adapter to them. 4N and 4T inherit
    the mechanism by being registered; they still have to supply their own
    product knowledge, which is irreducible.
    """

    def test_every_registered_adapter_declares_the_attribute(self) -> None:
        """Absent means "not considered", which must not look like "none"."""
        for product_type, adapter_cls in ADAPTER_REGISTRY.items():
            assert hasattr(adapter_cls, "unexposed_routes"), product_type
            assert isinstance(
                adapter_cls.unexposed_routes, tuple
            ), f"{product_type}: unexposed_routes must be a tuple"

    @pytest.mark.parametrize("product_type", sorted(p for p, _ in _adapters_with_rules()))
    def test_no_rule_admits_a_declared_unexposed_route(self, product_type: str) -> None:
        """The assertion the whole declaration exists for."""
        adapter_cls = ADAPTER_REGISTRY[product_type]
        rules = list(adapter_cls.route_allowlist)

        for method, path in adapter_cls.unexposed_routes:
            offenders = [rule.path_regex for rule in rules if rule.matches(method, path)]
            assert not offenders, (
                f"{product_type}: {method} {path} is declared unexposed but is "
                f"admitted by {offenders!r}. Either the rule's id pattern is "
                f"too loose, or the route genuinely should be allowlisted and "
                f"the declaration is stale."
            )

    @pytest.mark.parametrize("product_type", sorted(p for p, _ in _adapters_with_rules()))
    def test_an_adapter_with_id_patterns_must_declare_unexposed_routes(
        self, product_type: str
    ) -> None:
        """Where the hazard is possible, the declaration is mandatory.

        A variable id segment is exactly the condition under which a product
        literal can be swallowed. An adapter whose rules are all literals
        (the Nest/Tobogganing stubs today) has no such hazard and is correctly
        exempt — requiring a declaration from them would be noise that teaches
        the next author the field is ceremonial.
        """
        adapter_cls = ADAPTER_REGISTRY[product_type]
        has_variable_segment = any(
            not _is_literal(segment)
            for rule in adapter_cls.route_allowlist
            for segment in _rule_segments(rule)
        )
        if not has_variable_segment:
            pytest.skip(f"{product_type} declares no variable id segments")

        assert adapter_cls.unexposed_routes, (
            f"{product_type} uses variable id segments but declares no "
            f"unexposed_routes. An id pattern can only be shown to be tight "
            f"against the product routes it must not match — declare them."
        )

    def test_gough_declares_the_route_that_caused_the_defect(self) -> None:
        """Regression: the enrollment-keys endpoint must be named explicitly.

        This is the route a loose ``[^/]+`` agent-id pattern allowlisted — it
        lists agent enrollment credentials. Naming it in the contract is what
        turns "the pattern looks tight" into an assertion about the specific
        endpoint at risk.
        """
        declared = set(ADAPTER_REGISTRY["gough"].unexposed_routes)
        assert ("GET", "/api/v1/agents/enrollment-keys") in declared
        assert ("POST", "/api/v1/agents/enroll") in declared
        assert ("POST", "/api/v1/auth/login") in declared

    def test_a_loose_id_pattern_is_caught_by_the_declaration(self) -> None:
        """Prove the mechanism catches the original defect.

        Rebuilds Gough's allowlist with the untyped agent-id slot it used to
        have and asserts the declaration refuses it. Without this, the
        declaration could be a list nothing ever reads.
        """
        loose = [RouteRule("GET", r"^/api/v1/agents/[^/]+\Z", "products:gough:read")]
        hazard = ("GET", "/api/v1/agents/enrollment-keys")

        assert any(rule.matches(*hazard) for rule in loose), (
            "the loose pattern must admit the hazard — otherwise this test "
            "proves nothing about the check that refuses it"
        )
