"""Adapter contract v2 — the guarantees Phase 4 builds three adapters on.

Everything here is a contract-level property rather than a portal behaviour:
these are the rules that must hold for an adapter nobody has written yet.
The point of testing them at construction time is that a misdeclared rule
should fail at import, loudly, rather than over-match silently in production.
"""

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from app.adapters.base import (
    DEFAULT_PATH_SUBSTITUTIONS,
    TENANT_PLACEHOLDER,
    TENANT_PLACEHOLDER_PATTERN,
    AdapterCapabilityError,
    AdapterContext,
    AdapterError,
    MetricPoint,
    MetricSeries,
    MetricsSummary,
    Page,
    PathSubstitution,
    PathTraversalError,
    RateLimitedError,
    Resource,
    ResourceConflictError,
    ResourceNotFoundError,
    RouteRule,
    TimeRange,
    UpstreamAuthError,
    UpstreamError,
    adapter_error_status,
    normalize_proxy_path,
)


def _ctx(base_url: str = "https://p.invalid") -> AdapterContext:
    """A minimal context for transport-level assertions."""
    return AdapterContext(
        connection_id=1,
        portal_tenant_id=2,
        external_id="ext-1",
        external_kind="tenant_id",
        base_url=base_url,
        auth_type="bearer",
        api_key="a-credential",
    )


class TestRouteRuleAnchoring:
    """A rule that is not fully anchored must not be constructible."""

    def test_unanchored_start_is_rejected_at_construction(self) -> None:
        """``/users`` without ``^`` matches anywhere in the path."""
        with pytest.raises(ValueError, match="start-anchored"):
            RouteRule("GET", r"/users\Z", "products:read")

    def test_unanchored_end_is_rejected_at_construction(self) -> None:
        """The defect this exists for: ``^/users`` also admits ``/users/../admin``.

        Every shipped adapter hand-anchoring correctly is a property that
        lasts until the next author. Rejecting at construction makes a
        misdeclared rule an ImportError in CI, not a quiet over-match.
        """
        with pytest.raises(ValueError, match="end-anchored"):
            RouteRule("GET", r"^/users", "products:read")

    def test_dollar_anchor_is_rejected_in_favour_of_z_anchor(self) -> None:
        r"""``$`` also matches before a trailing newline; ``\Z`` does not."""
        with pytest.raises(ValueError, match=r"trailing\s+newline"):
            RouteRule("GET", r"^/health$", "products:read")

    def test_uncompilable_pattern_is_rejected(self) -> None:
        """A broken regex fails at import, not on the first request."""
        with pytest.raises(ValueError, match="does not compile"):
            RouteRule("GET", r"^/users([\Z", "products:read")

    def test_unknown_method_is_rejected(self) -> None:
        """A rule the proxy could never dispatch is a declaration bug."""
        with pytest.raises(ValueError, match="not an HTTP method"):
            RouteRule("FETCH", r"^/users\Z", "products:read")

    def test_empty_scope_is_rejected(self) -> None:
        """An allowlist entry with no scope would be an unguarded route."""
        with pytest.raises(ValueError, match="required_scope"):
            RouteRule("GET", r"^/users\Z", "")

    def test_trailing_newline_does_not_match(self) -> None:
        r"""The concrete ``$`` hazard, asserted end to end.

        Even with ``\Z`` enforced at construction, matching uses
        ``re.fullmatch`` so anchoring holds structurally if a future edit
        weakens the pattern text.
        """
        rule = RouteRule("GET", r"^/health\Z", "products:read")

        assert rule.matches("GET", "/health") is True
        assert rule.matches("GET", "/health\n") is False

    def test_rule_does_not_match_a_traversal_of_its_own_prefix(self) -> None:
        r"""``^/users(/.*)?\\Z`` must not admit ``/users/../admin``.

        Anchoring alone does not settle this — ``/users/../admin`` genuinely
        matches ``^/users(/.*)?\\Z``. The path is refused as malformed before
        the pattern is consulted.
        """
        rule = RouteRule("GET", r"^/users(/.*)?\Z", "products:read")

        assert rule.matches("GET", "/users/7") is True
        assert rule.matches("GET", "/users/../admin") is False

    def test_method_is_part_of_the_rule(self) -> None:
        """A declared path is not a free pass for every verb."""
        rule = RouteRule("GET", r"^/health\Z", "products:read")

        assert rule.matches("get", "/health") is True
        assert rule.matches("POST", "/health") is False


class TestPathNormalization:
    """What the proxy refuses before anything is matched or dispatched."""

    @pytest.mark.parametrize(
        "path",
        [
            "/users/../admin",
            "/./users",
            "/users/..",
            "/a/b/../../etc/passwd",
        ],
    )
    def test_dot_segments_are_refused(self, path: str) -> None:
        """Refused, never resolved — see normalize_proxy_path's docstring."""
        with pytest.raises(PathTraversalError):
            normalize_proxy_path(path)

    @pytest.mark.parametrize("path", ["/%2e%2e/admin", "/%2E%2E/admin", "/a/%2e/b"])
    def test_encoded_dots_are_refused(self, path: str) -> None:
        """A percent-encoded dot in an already-decoded path is double-encoding.

        It has exactly one purpose: surviving the portal's decode so the
        product performs the second decode and the traversal lands there.
        """
        with pytest.raises(PathTraversalError):
            normalize_proxy_path(path)

    @pytest.mark.parametrize(
        "path",
        [
            # The original defect, verbatim. The segment scan splits on a
            # LITERAL slash, so this is ONE segment ("..%2fadmin") to the
            # portal and two to any product that decodes it.
            "/users/..%2fadmin",
            "/nodes/..%2Fadmin",
            # Encoded backslash: same trick where the product treats "\" as a
            # separator. Note the LITERAL backslash check cannot see this one.
            "/users/..%5cadmin",
            "/users/..%5Cadmin",
            # Without any dot at all — proves the rejection is the separator
            # itself, not a dot heuristic reaching it by luck.
            "/nodes/foo%2fbar",
            "/nodes/foo%5cbar",
        ],
    )
    def test_encoded_separators_are_refused(self, path: str) -> None:
        """I2: only ``_ENCODED_SEPARATOR`` can reject these — that is the point.

        Every case here is chosen so that removing the encoded-separator check
        makes it PASS, which is what a regression test for that check has to
        do. Each one is deliberately invisible to every other guard in
        ``normalize_proxy_path``:

        * the dot-segment scan sees ``..%2fadmin``, which is not ``..``;
        * the ``%2e`` check does not fire — there is no encoded dot;
        * the literal-backslash check does not fire — ``%5c`` is encoded;
        * the last two contain no dots at all.

        The pre-existing coverage for this went through the Gough allowlist,
        where ``_INT_ID`` refuses a non-numeric id regardless — so it stayed
        green with the check deleted and could not detect its removal.
        """
        with pytest.raises(PathTraversalError):
            normalize_proxy_path(path)

    def test_encoded_separator_check_is_load_bearing(self) -> None:
        """State the property directly: no other guard covers these.

        If a future edit makes one of these reachable by a different check,
        this still passes — but the parametrised cases above are what break
        loudly if the encoded-separator guard is dropped outright.
        """
        # No control chars, no literal backslash, no %2e, no bare dot segment.
        hostile = "/users/..%2fadmin"
        assert "\\" not in hostile
        assert "%2e" not in hostile.lower()
        assert ".." not in hostile.split("/")
        with pytest.raises(PathTraversalError):
            normalize_proxy_path(hostile)

    def test_backslash_is_refused(self) -> None:
        r"""Some servers treat ``\\`` as a separator, making ``..\\`` traversal."""
        with pytest.raises(PathTraversalError):
            normalize_proxy_path("/users\\..\\admin")

    @pytest.mark.parametrize("path", ["/users\nX-Injected: 1", "/users\r\n", "/u\x00b"])
    def test_control_characters_are_refused(self, path: str) -> None:
        """CR/LF in a path is request smuggling and log injection."""
        with pytest.raises(PathTraversalError):
            normalize_proxy_path(path)

    def test_interior_empty_segment_is_refused(self) -> None:
        """``//`` collapses differently across servers, so it is ambiguous."""
        with pytest.raises(PathTraversalError):
            normalize_proxy_path("/users//7")

    def test_ordinary_paths_survive_with_a_leading_slash(self) -> None:
        """Normalization is a gate, not a rewriter."""
        assert normalize_proxy_path("/users/7") == "/users/7"
        assert normalize_proxy_path("users/7") == "/users/7"
        assert normalize_proxy_path("/users/") == "/users/"
        assert normalize_proxy_path("/a.b/c-d_e~f") == "/a.b/c-d_e~f"


class TestDeclaredSubstitution:
    """Placeholder substitution is declared, not folklore."""

    def test_default_substitution_maps_tenant_to_the_mapped_external_id(self) -> None:
        """The one substitution every adapter gets, stated in the contract."""
        assert DEFAULT_PATH_SUBSTITUTIONS == (PathSubstitution(TENANT_PLACEHOLDER, "external_id"),)

    def test_substitution_must_name_a_real_context_field(self) -> None:
        """A typo'd attribute would silently substitute an empty string."""
        with pytest.raises(ValueError, match="AdapterContext field"):
            PathSubstitution("{org}", "not_a_field")

    def test_substitution_values_can_only_come_from_the_context(self) -> None:
        """Every AdapterContext field is server-derived.

        Restricting substitution sources to the context is what makes "a
        caller cannot interpolate their own value" true by construction
        rather than by the proxy remembering to check.
        """
        for field in AdapterContext.__slots__:
            assert PathSubstitution("{x}", field).context_attr == field

    def test_placeholder_pattern_is_regex_safe(self) -> None:
        """Braces are repetition syntax; the exported pattern is pre-escaped.

        Hand-escaping is the trap: an unescaped ``{tenant}`` in a pattern is
        the kind of thing that either works by accident or never matches,
        and the difference is not visible in review.
        """
        rule = RouteRule("GET", rf"^/orgs/{TENANT_PLACEHOLDER_PATTERN}/vms\Z", "products:read")

        assert rule.matches("GET", "/orgs/{tenant}/vms") is True
        assert rule.matches("GET", "/orgs/somebody-else/vms") is False


class TestErrorTaxonomy:
    """Phase 4 has names for the failures it will hit."""

    @pytest.mark.parametrize(
        ("error", "status"),
        [
            (AdapterCapabilityError("x"), 501),
            (ResourceNotFoundError("x"), 404),
            (ResourceConflictError("x"), 409),
            (RateLimitedError("x"), 429),
            (UpstreamAuthError("x"), 502),
            (UpstreamError("x"), 502),
        ],
    )
    def test_each_member_maps_to_one_status(self, error: AdapterError, status: int) -> None:
        """Defined once, so three adapters cannot invent three mappings."""
        assert adapter_error_status(error) == status

    def test_unmapped_subclass_falls_back_to_upstream_failure(self) -> None:
        """An unrecognised adapter failure is still an upstream failure.

        Never a 200, and never a 500 blaming the portal for a product's
        behaviour.
        """

        class NovelFailureError(AdapterError):
            """A subclass added without a mapping."""

        assert adapter_error_status(NovelFailureError("x")) == 502

    def test_everything_shares_one_base(self) -> None:
        """One ``except AdapterError`` catches the whole taxonomy."""
        for error in (
            AdapterCapabilityError("x"),
            ResourceNotFoundError("x"),
            ResourceConflictError("x"),
            RateLimitedError("x"),
            UpstreamAuthError("x"),
            UpstreamError("x"),
        ):
            assert isinstance(error, AdapterError)

    def test_rate_limit_carries_the_products_retry_delay(self) -> None:
        """Backing off correctly needs the number, not just the category."""
        assert RateLimitedError("slow down", retry_after=30.0).retry_after == 30.0
        assert RateLimitedError("slow down").retry_after is None

    def test_not_found_is_not_a_capability_gap(self) -> None:
        """Distinct types because they are distinct answers.

        Collapsing them makes a missing integration look like an empty
        account, which is the reading that ships a dashboard reporting zero
        of everything.
        """
        assert not isinstance(ResourceNotFoundError("x"), AdapterCapabilityError)


class TestDashboardShapes:
    """Resource / Page / MetricsSummary carry what a dashboard renders."""

    def test_resource_carries_state_timestamps_and_a_parent_edge(self) -> None:
        """The fields a generic dashboard needs are named, not metadata keys."""
        now = datetime.now(UTC)
        resource = Resource(
            id="vm-1",
            kind="vm",
            name="web-01",
            status="running",
            created_at=now,
            updated_at=now,
            parent_id="cluster-9",
            parent_kind="cluster",
        )

        assert resource.status == "running"
        assert resource.parent_id == "cluster-9"
        assert resource.created_at == now
        assert resource.metadata == {}

    def test_resource_optional_fields_default_to_absent(self) -> None:
        """A product that reports no state says so; nothing is invented."""
        resource = Resource(id="x", kind="k", name="n")

        assert resource.status is None
        assert resource.created_at is None
        assert resource.parent_id is None

    def test_page_supports_cursor_pagination_without_a_total(self) -> None:
        """Nest and Tobogganing paginate by cursor and report no count.

        A mandatory ``total`` forces those adapters to fabricate one, and a
        fabricated total is worse than an absent one because the UI renders
        it as fact.
        """
        page: Page[Resource] = Page(items=[], cursor="c1", next_cursor="c2", has_more=True)

        assert page.total is None
        assert page.has_more is True
        assert page.next_cursor == "c2"

    def test_page_supports_offset_pagination(self) -> None:
        """The offset style still works, unchanged in meaning."""
        page: Page[Resource] = Page(items=[], page=2, per_page=50, total=120, has_more=True)

        assert (page.page, page.per_page, page.total) == (2, 50, 120)
        assert page.cursor is None

    def test_last_page_reports_no_more(self) -> None:
        """``has_more`` is answerable by both paginators; ``total`` is not."""
        page: Page[Resource] = Page(items=[], has_more=False)

        assert page.has_more is False
        assert page.next_cursor is None

    def test_metrics_summary_is_renderable_without_product_knowledge(self) -> None:
        """A time range plus named, united series is the minimum shape.

        ``dict[str, Any]`` could not be charted without per-product
        knowledge — the one thing a generic portal dashboard cannot have.
        """
        start = datetime(2026, 1, 1, tzinfo=UTC)
        end = datetime(2026, 1, 2, tzinfo=UTC)
        summary = MetricsSummary(
            range=TimeRange(start=start, end=end),
            series=[
                MetricSeries(
                    key="cpu",
                    label="CPU",
                    unit="percent",
                    points=[MetricPoint(timestamp=start, value=42.0)],
                )
            ],
            totals={"vms": 3.0},
        )

        assert summary.range.start == start
        assert summary.series[0].unit == "percent"
        assert summary.series[0].points[0].value == 42.0
        assert summary.totals["vms"] == 3.0

    def test_metrics_summary_defaults_to_an_empty_but_valid_shape(self) -> None:
        """A range is always required; series and totals may legitimately be empty."""
        summary = MetricsSummary(
            range=TimeRange(
                start=datetime(2026, 1, 1, tzinfo=UTC),
                end=datetime(2026, 1, 2, tzinfo=UTC),
            )
        )

        assert summary.series == []
        assert summary.totals == {}


@pytest.mark.asyncio
class TestCredentialEgressPin:
    """Where the stored credential may go — the structural half of B1.

    The route allowlist governs which caller-supplied paths are forwarded.
    It says nothing about adapter methods, which are trusted server-side
    code. The pin is what bounds that trust: whatever an adapter does, the
    credential reaches the connection's own origin or no origin at all.
    """

    @staticmethod
    def _transport(handler: object) -> object:
        """A Transport wired to an in-process handler instead of a socket."""
        from app.adapters.transport import Transport

        instance = Transport(timeout=10.0)
        instance._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
            timeout=httpx.Timeout(10.0),
        )
        return instance

    async def test_request_to_the_pinned_origin_is_allowed(self) -> None:
        """The ordinary case still works."""
        transport = self._transport(lambda request: httpx.Response(200, content=b"ok"))

        response = await transport.request(  # type: ignore[attr-defined]
            "GET", "https://p.invalid/healthz", _ctx()
        )

        assert response.status_code == 200

    @pytest.mark.parametrize(
        "url",
        [
            "https://attacker.invalid/steal",
            "http://p.invalid/healthz",  # scheme downgrade
            "https://p.invalid.attacker.invalid/x",  # suffix confusion
            "https://169.254.169.254/latest/meta-data/",  # cloud metadata
        ],
    )
    async def test_request_off_the_pinned_origin_is_refused(self, url: str) -> None:
        """No outbound call is made at all, so nothing leaks in flight."""
        from app.adapters.transport import CredentialEgressError

        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200)

        transport = self._transport(handler)

        with pytest.raises(CredentialEgressError):
            await transport.request("GET", url, _ctx())  # type: ignore[attr-defined]

        assert calls == [], "credential was sent before the pin was checked"

    async def test_connection_without_a_base_url_pins_to_nothing(self) -> None:
        """An unusable base_url is refused, not read as 'no restriction'."""
        from app.adapters.transport import CredentialEgressError

        transport = self._transport(lambda request: httpx.Response(200))

        with pytest.raises(CredentialEgressError):
            await transport.request(  # type: ignore[attr-defined]
                "GET", "https://p.invalid/x", _ctx(base_url="")
            )

    async def test_redirects_are_never_followed(self) -> None:
        """A 302 off-origin would carry the credential past the pin.

        The pin checks the URL the transport is asked for; a redirect chased
        inside httpx would never reach it.
        """
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return httpx.Response(302, headers={"location": "https://evil.invalid/x"})

        transport = self._transport(handler)
        response = await transport.request(  # type: ignore[attr-defined]
            "GET", "https://p.invalid/healthz", _ctx()
        )

        assert response.status_code == 302
        assert seen == ["https://p.invalid/healthz"]

    async def test_oversized_body_is_refused_before_it_is_buffered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The declared length is checked first, so no chunk is read.

        The previous implementation measured ``len(response.content)`` after
        httpx had already buffered everything, which made the memory-
        exhaustion claim in its docstring false.
        """
        import app.adapters.transport as transport_module

        monkeypatch.setattr(transport_module, "MAX_RESPONSE_SIZE", 64)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=b"z" * 4096,
                headers={"content-length": "4096"},
            )

        transport = self._transport(handler)

        with pytest.raises(transport_module.ResponseTooLargeError):
            await transport.request(  # type: ignore[attr-defined]
                "GET", "https://p.invalid/x", _ctx()
            )

    async def test_undeclared_oversized_body_is_stopped_mid_stream(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Chunked responses declare no length, so the read enforces the bound."""
        import app.adapters.transport as transport_module

        monkeypatch.setattr(transport_module, "MAX_RESPONSE_SIZE", 64)

        emitted = {"chunks": 0}

        async def _chunks() -> Any:
            # No content-length: this is what a chunked product looks like.
            for _ in range(100):
                emitted["chunks"] += 1
                yield b"z" * 32

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=_chunks())

        transport = self._transport(handler)

        with pytest.raises(transport_module.ResponseTooLargeError):
            await transport.request(  # type: ignore[attr-defined]
                "GET", "https://p.invalid/x", _ctx()
            )

        # Stopped early: the whole 3200-byte body was never accumulated.
        assert emitted["chunks"] < 100
