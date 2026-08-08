"""Adapter Contract v2 — typed async Protocol, DTOs, and the security boundary.

Which path is the security boundary
===================================
There are two ways a portal request reaches a connected product, and they are
NOT equally trusted. Phase 4 integrators must not have to infer this:

1. **The passthrough proxy** (``app/proxy.py``) — the UNTRUSTED-INPUT path.
   The caller supplies the path, the method, the query string and the body,
   and the portal forwards them largely unexamined. This is the path
   :attr:`Adapter.route_allowlist` governs, and it is deny-by-default: a
   request that matches no declared :class:`RouteRule` is refused before any
   outbound call is made. The allowlist exists to constrain *a string the
   browser controls*.

2. **Adapter methods** (``list_resources``, ``create_resource``, …) — TRUSTED
   server-side code. They take typed arguments, build their own URLs from
   module literals, and are reached only through a portal route that has
   already enforced a scope with ``@require_scope``. They deliberately do
   **not** re-check ``route_allowlist``, because there is no caller-supplied
   path to check: a rule would be satisfied by construction, and a check that
   can never fail is one nobody maintains — while implying, falsely, that the
   allowlist is what makes these methods safe.

What actually makes adapter methods safe is therefore *not* the allowlist:

* they expose typed operations, never a free-form path;
* scope enforcement happens at the portal route that calls them;
* and every outbound call — proxied or not — goes through
  :mod:`app.adapters.transport`, which pins the request to the connection's
  own origin (:class:`AdapterContext.base_url`), refuses to follow
  redirects, caps the response, and injects the credential itself.

That last point is the structural half of this decision, and it is what
makes "adapter methods are trusted" a bounded claim rather than a promise:
**the allowlist decides which caller-supplied paths are forwarded; the
transport decides where the stored credential may go.** An adapter that
tried to route a caller-influenced value to another host does not get a
policy violation, it gets a
:class:`~app.adapters.transport.CredentialEgressError`.

Consequence for Phase 4: put untrusted input through the proxy and declare a
``RouteRule`` for it. Do not accept a caller-supplied path into an adapter
method and hand it to ``transport.request`` — that is the one way to move
work from column 1 to column 2 without the review column 1 gets.

Path matching happens BEFORE tenant substitution
================================================
A :class:`RouteRule` describes the path *as the caller writes it*, which is
why a rule for a tenant-addressed route contains the placeholder literally.
Import :data:`TENANT_PLACEHOLDER_PATTERN` rather than hand-escaping it; the
braces are regex metacharacters and getting that wrong yields a rule that
silently never matches. See :class:`PathSubstitution`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final, Generic, Protocol, TypeVar

__all__ = [
    "HealthResult",
    "Resource",
    "Page",
    "MetricPoint",
    "MetricSeries",
    "MetricsSummary",
    "TimeRange",
    "AdapterContext",
    "PathSubstitution",
    "RouteRule",
    "RBACEnforcer",
    "AdapterError",
    "AdapterCapabilityError",
    "ResourceNotFoundError",
    "ResourceConflictError",
    "RateLimitedError",
    "UpstreamAuthError",
    "UpstreamError",
    "PathTraversalError",
    "adapter_error_status",
    "normalize_proxy_path",
    "TENANT_PLACEHOLDER",
    "TENANT_PLACEHOLDER_PATTERN",
    "HealthOnlyAdapter",
    "Adapter",
]


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------


class AdapterError(Exception):
    """Base for every failure an adapter is allowed to surface.

    Phase 4 adapters raise one of the subclasses below rather than letting an
    ``httpx.HTTPStatusError`` escape: a raw transport exception carries the
    product's URL and headers into the portal's error path, and forces every
    caller to re-derive what a given upstream status means.
    """


class AdapterCapabilityError(AdapterError):
    """Raised when an adapter does not support a requested operation."""


class ResourceNotFoundError(AdapterError):
    """The product does not have the requested resource.

    Distinct from :class:`AdapterCapabilityError`: "this portal cannot list
    widgets" and "this product has no widget 7" are different answers, and
    collapsing them makes a missing integration look like an empty account.
    """


class ResourceConflictError(AdapterError):
    """The product refused the write as conflicting with current state.

    Duplicate unique key, edit against a stale version, delete of something
    still referenced. Retrying is pointless; the caller must re-read.
    """


class RateLimitedError(AdapterError):
    """The product is rate-limiting the portal.

    ``retry_after`` is seconds, taken from the product's header when it sent
    one. Kept as its own class so callers can back off instead of treating a
    throttle as an outage.
    """

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        """Record the message and the product's advertised retry delay."""
        super().__init__(message)
        self.retry_after = retry_after


class UpstreamAuthError(AdapterError):
    """The product rejected the portal's *stored* credential.

    Never a statement about the portal caller's own authorization — it means
    the connection needs re-credentialing by an operator. Surfacing it as 401
    would tell the browser to re-login, which fixes nothing.
    """


class UpstreamError(AdapterError):
    """The product failed in a way with no more specific meaning."""


class PathTraversalError(ValueError):
    """A request path contained dot-segments or control characters."""


#: How each taxonomy member renders at the portal's API boundary. Defined
#: once so three Phase-4 adapters cannot each invent their own mapping.
_ERROR_STATUS: Final[tuple[tuple[type[AdapterError], int], ...]] = (
    (AdapterCapabilityError, 501),
    (ResourceNotFoundError, 404),
    (ResourceConflictError, 409),
    (RateLimitedError, 429),
    (UpstreamAuthError, 502),
    (UpstreamError, 502),
)


def adapter_error_status(exc: AdapterError) -> int:
    """Map an adapter error onto the HTTP status the portal should return.

    Falls back to 502 for an ``AdapterError`` subclass added without a
    mapping: an unrecognised adapter failure is still an upstream failure,
    never a 200 and never a 500 blamed on the portal.
    """
    for error_type, status in _ERROR_STATUS:
        if isinstance(exc, error_type):
            return status
    return 502


# ---------------------------------------------------------------------------
# Result DTOs
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class HealthResult:
    """Health check result from an adapter."""

    status: str  # healthy, degraded, unhealthy
    status_code: int
    response_time_ms: int
    error: str | None = None


@dataclass(slots=True)
class Resource:
    """A single object in a connected product, in the portal's own shape.

    The optional fields are what a dashboard is actually built from and are
    therefore part of the contract rather than free-form ``metadata`` keys
    three adapters would each spell differently:

    * ``status`` — the product's lifecycle state, verbatim (``running``,
      ``suspended``, ``provisioning``). Not normalised to a portal
      vocabulary, because collapsing a product's states loses the
      distinction an operator is looking at the dashboard to see.
    * ``created_at`` / ``updated_at`` — timezone-aware, so sorting and
      "changed recently" work without the portal parsing product-specific
      timestamp strings.
    * ``parent_id`` / ``parent_kind`` — the relationship edge. Products are
      hierarchical (a VM in a cluster, a bucket in a project), and without
      an edge the portal can only ever render flat lists.

    ``metadata`` stays for genuinely product-specific extras; anything the
    portal renders generically belongs in a named field.
    """

    id: str
    kind: str
    name: str
    status: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    parent_id: str | None = None
    parent_kind: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


T = TypeVar("T")


@dataclass(slots=True)
class Page(Generic[T]):
    """One page of results, from either an offset or a cursor paginator.

    ``total`` is OPTIONAL on purpose. Nest and Tobogganing paginate by
    cursor and never return a count; a mandatory ``total`` forces those
    adapters to either fabricate one or issue a second counting request per
    page. A fabricated total is worse than an absent one — the UI renders it
    as fact.

    ``has_more`` is the field a caller should branch on: it is answerable by
    both paginator styles, whereas ``page < total / per_page`` is answerable
    by neither when ``total`` is unknown.
    """

    items: list[T]
    #: Offset pagination: 1-based page number. Meaningless for cursor
    #: paginators, which leave it at its default.
    page: int = 1
    per_page: int = 20
    #: Absent when the product does not report one — see class docstring.
    total: int | None = None
    #: Cursor pagination: the opaque cursor that produced THIS page.
    cursor: str | None = None
    #: Opaque cursor for the next page; None when this is the last page.
    next_cursor: str | None = None
    #: True when another page exists, however the product paginates.
    has_more: bool = False


@dataclass(slots=True, frozen=True)
class TimeRange:
    """The window a metrics summary covers. Both bounds timezone-aware."""

    start: datetime
    end: datetime


@dataclass(slots=True, frozen=True)
class MetricPoint:
    """One sample in a series."""

    timestamp: datetime
    value: float


@dataclass(slots=True)
class MetricSeries:
    """A named, unit-carrying sequence of samples.

    ``unit`` is required rather than optional: a chart axis cannot be
    rendered from a bare number, and an adapter that omits it forces the
    portal to guess between bytes, percent and count.
    """

    key: str
    label: str
    unit: str
    points: list[MetricPoint] = field(default_factory=list)


@dataclass(slots=True)
class MetricsSummary:
    """Typed return of :meth:`Adapter.metrics_summary`.

    Previously ``dict[str, Any]``, which the portal could not render without
    per-product knowledge — the one thing a generic dashboard cannot have.
    A time range plus named, united series is the minimum shape that lets one
    chart component draw any product's metrics.

    ``totals`` carries scalar headline figures (``{"vms": 42.0}``) that have
    no time dimension, for the counter tiles above the charts.
    """

    range: TimeRange
    series: list[MetricSeries] = field(default_factory=list)
    totals: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class AdapterContext:
    """Immutable context for adapter operations.

    Carried through every adapter call to provide tenant/connection info,
    scopes, and correlation tracking.
    """

    connection_id: int
    portal_tenant_id: int
    external_id: str  # from product_tenant_map
    external_kind: str  # from product_tenant_map
    base_url: str
    auth_type: str  # bearer, api_key, basic, none
    api_key: str  # decrypted
    api_secret: str = ""  # decrypted, if applicable
    correlation_id: str = ""
    scopes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Path handling
# ---------------------------------------------------------------------------

#: Literal an adapter writes in a route to mark where the product's own
#: tenant identifier belongs. The caller never supplies the value — they
#: address their portal tenant and the mapped external id is spliced in
#: server-side.
TENANT_PLACEHOLDER: Final[str] = "{tenant}"

#: The same placeholder, pre-escaped for use inside a ``path_regex``. Braces
#: are regex repetition syntax; import this rather than hand-escaping::
#:
#:     RouteRule("GET", rf"^/orgs/{TENANT_PLACEHOLDER_PATTERN}/vms\Z", ...)
TENANT_PLACEHOLDER_PATTERN: Final[str] = re.escape(TENANT_PLACEHOLDER)

#: Percent-encoded dot, in any case. Its presence in an ALREADY-decoded path
#: means the caller double-encoded, which only has a purpose if the intent
#: is for the product to decode it a second time into a traversal.
_ENCODED_DOT = re.compile(r"%2e", re.IGNORECASE)

_ALLOWED_METHODS: Final[frozenset[str]] = frozenset(
    {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
)


def normalize_proxy_path(raw: str) -> str:
    """Validate a caller-supplied proxy path, or refuse it.

    Rejects rather than rewrites. Resolving ``/users/../admin`` to ``/admin``
    would mean the allowlist judged one string and the product received
    another, and any disagreement between the portal's normaliser and the
    product's is a bypass. A caller with a legitimate request has no reason
    to send a dot-segment, so refusing costs nothing and removes the whole
    class.

    Refused:

    * ``.`` / ``..`` segments — the traversal itself. ``re.match(r"/users",
      "/users/../admin")`` is a match, so an allowlist alone does not stop it.
    * percent-encoded dots — a double-encoded traversal that survives the
      portal's decode and unfolds at the product.
    * backslashes — treated as a separator by some servers, so ``..\\`` is a
      traversal on those and invisible here.
    * control characters — CR/LF in a path is request smuggling against the
      product and log injection on the way there.
    * interior empty segments (``//``) — collapse differently across servers,
      so what the allowlist matched need not be what the product routes.

    Returns the path with a leading slash guaranteed.

    Raises:
        PathTraversalError: on any of the above.
    """
    if not raw.startswith("/"):
        raw = "/" + raw

    for char in raw:
        if char < "\x20" or char == "\x7f":
            raise PathTraversalError("path contains a control character")
    if "\\" in raw:
        raise PathTraversalError("path contains a backslash")
    if _ENCODED_DOT.search(raw):
        raise PathTraversalError("path contains a percent-encoded dot segment")

    segments = raw.split("/")
    last = len(segments) - 1
    for index, segment in enumerate(segments[1:], start=1):
        if segment in (".", ".."):
            raise PathTraversalError("path contains a dot segment")
        if segment == "" and index != last:
            raise PathTraversalError("path contains an empty segment")

    return raw


@dataclass(slots=True, frozen=True)
class PathSubstitution:
    """Declares one placeholder an adapter's routes may carry.

    Substitution used to be a single hard-coded ``{tenant}`` literal known
    only to the proxy, documented nowhere and discoverable only by reading a
    test. Declaring it per adapter means a Phase-4 adapter that addresses its
    product by something other than the mapped tenant id (an org slug, a
    project id) says so in its own module instead of the proxy growing a
    branch per product.

    ``context_attr`` names an attribute of :class:`AdapterContext`; the proxy
    reads it and URL-quotes the value. It is deliberately restricted to
    context attributes — every one of them is server-derived, so no
    substitution can ever interpolate something the caller sent.
    """

    placeholder: str
    context_attr: str

    def __post_init__(self) -> None:
        """Reject a substitution that names something the context lacks."""
        if not self.placeholder:
            raise ValueError("placeholder must not be empty")
        if self.context_attr not in AdapterContext.__slots__:
            raise ValueError(
                f"PathSubstitution context_attr {self.context_attr!r} is not an "
                f"AdapterContext field"
            )


#: What every adapter gets unless it declares otherwise: the portal tenant
#: becomes the product's own identifier from ``product_tenant_map``.
DEFAULT_PATH_SUBSTITUTIONS: Final[tuple[PathSubstitution, ...]] = (
    PathSubstitution(TENANT_PLACEHOLDER, "external_id"),
)


@dataclass(slots=True, frozen=True)
class RouteRule:
    """One declarative entry in an adapter's deny-by-default proxy allowlist.

    The pattern must be fully anchored — ``^`` at the start and ``\\Z`` at the
    end — and construction raises :class:`ValueError` when it is not. A
    misdeclared rule must fail loudly at import time, because the failure mode
    is silent over-matching: ``^/users`` (start-anchored only) also admits
    ``/users/../admin``, and every shipped adapter hand-anchoring correctly is
    a property that lasts exactly until the next author.

    ``\\Z`` rather than ``$`` because ``$`` also matches immediately before a
    trailing newline, so ``^/health$`` accepts ``/health\\n``.

    Matching is performed with :func:`re.fullmatch` as well, so anchoring
    holds structurally even if a future edit weakens the pattern text.

    The path is matched as the CALLER wrote it, before tenant substitution —
    see the module docstring and :class:`PathSubstitution`.
    """

    method: str  # GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS
    path_regex: str  # e.g. r'^/users(/[^/]+)?\Z'
    required_scope: str  # e.g. 'products:read', 'products:manage'

    def __post_init__(self) -> None:
        """Reject an unanchored, unknown-method or uncompilable rule."""
        if self.method.upper() not in _ALLOWED_METHODS:
            raise ValueError(
                f"RouteRule method {self.method!r} is not an HTTP method the "
                f"proxy serves ({sorted(_ALLOWED_METHODS)})"
            )
        if not self.required_scope:
            raise ValueError("RouteRule must declare a required_scope")
        if not self.path_regex.startswith("^"):
            raise ValueError(
                f"RouteRule path_regex {self.path_regex!r} is not start-anchored; "
                f"it must begin with '^'"
            )
        if not self.path_regex.endswith(r"\Z"):
            raise ValueError(
                f"RouteRule path_regex {self.path_regex!r} is not end-anchored; "
                f"it must end with '\\Z' ('$' also matches before a trailing "
                f"newline, so '^/health$' admits '/health\\n')"
            )
        try:
            re.compile(self.path_regex)
        except re.error as exc:
            raise ValueError(
                f"RouteRule path_regex {self.path_regex!r} does not compile: {exc}"
            ) from exc

    def matches(self, method: str, path: str) -> bool:
        """True if this rule allows the request.

        A path that fails :func:`normalize_proxy_path` matches nothing, so a
        caller cannot reach a declared route by a traversal even if some
        future caller forgets to normalise first.
        """
        if self.method.upper() != method.upper():
            return False
        try:
            candidate = normalize_proxy_path(path)
        except PathTraversalError:
            return False
        return re.fullmatch(self.path_regex, candidate) is not None


class Adapter(Protocol):
    """Protocol all adapters must implement.

    Adapters are instantiated per-request with AdapterContext carrying
    credentials, tenant mapping, and scopes. All methods are async.

    **These methods are the trusted path.** They are not filtered by
    ``route_allowlist``; that list governs only the passthrough proxy, which
    is where caller-supplied paths arrive. See the module docstring for the
    full statement of which path is the security boundary and why — an
    implementer who accepts a caller-supplied path here and hands it to
    ``transport.request`` has moved untrusted input into the trusted column.
    """

    #: Declarative allowlist of routes the PROXY may forward for this
    #: adapter. Deny-by-default: an empty list forwards nothing. Not
    #: consulted by the methods below.
    route_allowlist: list[RouteRule]

    #: Placeholders this adapter's routes may carry, and the AdapterContext
    #: attribute supplying each value.
    path_substitutions: tuple[PathSubstitution, ...]

    async def health(self, ctx: AdapterContext) -> HealthResult:
        """Check adapter health.

        Must return a HealthResult with status in (healthy, degraded, unhealthy).
        Timeouts and connection errors should return unhealthy with error message.
        """
        ...

    async def capabilities(self, ctx: AdapterContext) -> list[str]:
        """List capabilities supported by this adapter.

        E.g., ['health', 'list_resources', 'create_resource'].
        Raise AdapterCapabilityError if the adapter cannot list capabilities.
        """
        ...

    async def list_resources(
        self,
        kind: str,
        ctx: AdapterContext,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int = 20,
        cursor: str | None = None,
    ) -> Page[Resource]:
        """List resources of a given kind.

        ``cursor`` and ``page`` are alternatives: a cursor-paginated product
        ignores ``page``, an offset-paginated one ignores ``cursor``. Which
        one an adapter honours is reported by the ``Page`` it returns.

        Raise AdapterCapabilityError if kind is not supported.
        """
        ...

    async def get_resource(
        self, kind: str, resource_id: str, ctx: AdapterContext
    ) -> Resource:
        """Get a single resource by kind and ID.

        Raise ResourceNotFoundError when the product has no such resource,
        AdapterCapabilityError when this adapter does not handle ``kind``.
        """
        ...

    async def create_resource(
        self, kind: str, payload: dict[str, Any], ctx: AdapterContext
    ) -> Resource:
        """Create a resource of a given kind.

        Raise ResourceConflictError when the product refuses the write as
        conflicting, AdapterCapabilityError when the operation is unsupported.
        """
        ...

    async def update_resource(
        self, kind: str, resource_id: str, payload: dict[str, Any], ctx: AdapterContext
    ) -> Resource:
        """Update a resource of a given kind.

        Raise ResourceNotFoundError / ResourceConflictError /
        AdapterCapabilityError as appropriate.
        """
        ...

    async def delete_resource(
        self, kind: str, resource_id: str, ctx: AdapterContext
    ) -> None:
        """Delete a resource of a given kind.

        Raise ResourceNotFoundError / ResourceConflictError /
        AdapterCapabilityError as appropriate.
        """
        ...

    async def metrics_summary(self, ctx: AdapterContext) -> MetricsSummary:
        """Return a typed metrics summary the portal can render generically.

        Raise AdapterCapabilityError if the adapter does not expose metrics.
        """
        ...

    async def list_users(
        self, ctx: AdapterContext, page: int = 1, per_page: int = 20
    ) -> Page[dict[str, Any]]:
        """List users in the external tenant.

        Raise AdapterCapabilityError if the adapter does not support user listing.
        """
        ...

    async def invite_user(
        self, payload: dict[str, Any], ctx: AdapterContext
    ) -> dict[str, Any]:
        """Invite a user to the external tenant.

        Raise AdapterCapabilityError if the adapter does not support invitations.
        """
        ...


class HealthOnlyAdapter:
    """Base for an adapter that can prove liveness and nothing else.

    Phase 3 lands the contract, the transport and the deny-by-default proxy;
    the per-product resource operations are Phase 4 tasks. Rather than have
    each product's module repeat ten identical raising methods, they
    subclass this and declare only what distinguishes them: the product
    type, the display name, and their ``route_allowlist``.

    Every unimplemented operation raises :class:`AdapterCapabilityError`,
    which the API layer renders as 501. Notably it does NOT return an empty
    ``Page`` — a caller cannot tell "this product has no widgets" from "this
    portal cannot list widgets yet", and the first reading is the one that
    silently ships a dashboard reporting zero of everything.
    """

    #: Registry key. Subclasses must override.
    PRODUCT_TYPE: str = "unknown"

    #: Human-facing product name. Subclasses must override.
    DISPLAY_NAME: str = "Unknown Product"

    #: Path this adapter's health probe hits on the product.
    HEALTH_ENDPOINT: str = "/healthz"

    #: Deny-by-default proxy allowlist. An empty list means the proxy
    #: forwards nothing at all for this product, which is the correct
    #: default for one whose surface has not been reviewed.
    route_allowlist: list[RouteRule] = []

    #: The tenant placeholder, unless a product addresses its customers by
    #: something else. Declared here so it is legible from the contract
    #: rather than hard-coded in the proxy.
    path_substitutions: tuple[PathSubstitution, ...] = DEFAULT_PATH_SUBSTITUTIONS

    async def health(self, ctx: AdapterContext) -> HealthResult:
        """Probe the product's health endpoint."""
        from .transport import get_transport

        transport = await get_transport()
        return await transport.health_check(ctx.base_url, self.HEALTH_ENDPOINT, ctx)

    async def capabilities(self, ctx: AdapterContext) -> list[str]:
        """Report what this adapter can actually do today."""
        return ["health"]

    def _unsupported(self, operation: str) -> AdapterCapabilityError:
        """Build the error for an operation this adapter does not implement."""
        return AdapterCapabilityError(
            f"{operation} is not implemented for {self.PRODUCT_TYPE}"
        )

    async def list_resources(
        self,
        kind: str,
        ctx: AdapterContext,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int = 20,
        cursor: str | None = None,
    ) -> Page[Resource]:
        """Unsupported; raises AdapterCapabilityError."""
        raise self._unsupported(f"list_resources({kind})")

    async def get_resource(
        self, kind: str, resource_id: str, ctx: AdapterContext
    ) -> Resource:
        """Unsupported; raises AdapterCapabilityError."""
        raise self._unsupported(f"get_resource({kind})")

    async def create_resource(
        self, kind: str, payload: dict[str, Any], ctx: AdapterContext
    ) -> Resource:
        """Unsupported; raises AdapterCapabilityError."""
        raise self._unsupported(f"create_resource({kind})")

    async def update_resource(
        self, kind: str, resource_id: str, payload: dict[str, Any], ctx: AdapterContext
    ) -> Resource:
        """Unsupported; raises AdapterCapabilityError."""
        raise self._unsupported(f"update_resource({kind})")

    async def delete_resource(
        self, kind: str, resource_id: str, ctx: AdapterContext
    ) -> None:
        """Unsupported; raises AdapterCapabilityError."""
        raise self._unsupported(f"delete_resource({kind})")

    async def metrics_summary(self, ctx: AdapterContext) -> MetricsSummary:
        """Unsupported; raises AdapterCapabilityError."""
        raise self._unsupported("metrics_summary()")

    async def list_users(
        self, ctx: AdapterContext, page: int = 1, per_page: int = 20
    ) -> Page[dict[str, Any]]:
        """Unsupported; raises AdapterCapabilityError."""
        raise self._unsupported("list_users()")

    async def invite_user(
        self, payload: dict[str, Any], ctx: AdapterContext
    ) -> dict[str, Any]:
        """Unsupported; raises AdapterCapabilityError."""
        raise self._unsupported("invite_user()")


class RBACEnforcer:
    """Enforces role-based access control via scope matching.

    Shared between portal routes (@require_scope decorator) and proxy
    allowlist (RouteRule scope checks). Scopes are issued at token time
    and stored in the JWT; enforcement is zero-cost at request time.
    """

    def __init__(self, required_scopes: str | list[str]) -> None:
        """Initialize with required scope(s).

        Args:
            required_scopes: Single scope string or list of scopes.
                If list, ALL scopes in the list must be present (AND logic).
        """
        self.required_scopes = (
            required_scopes if isinstance(required_scopes, list) else [required_scopes]
        )

    def enforce(self, granted_scopes: list[str]) -> bool:
        """Check if granted scopes satisfy the requirement.

        Returns True if all required_scopes are in granted_scopes.
        """
        granted_set = set(granted_scopes)
        return all(scope in granted_set for scope in self.required_scopes)

    def enforce_or_raise(self, granted_scopes: list[str]) -> None:
        """Raise ValueError if granted scopes do not satisfy the requirement."""
        if not self.enforce(granted_scopes):
            missing = set(self.required_scopes) - set(granted_scopes)
            raise ValueError(f"Missing required scopes: {missing}")
