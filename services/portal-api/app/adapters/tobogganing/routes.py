"""Tobogganing route shapes, proxy allowlist, and the routes that must stay closed.

Every path Tobogganing is addressed by — by the proxy allowlist, by the typed
adapter methods, and (via the generated OpenAPI spec) by the web UI — is built
here, for the same reason Nest's is: Task 4G shipped a defect in which the
adapter and the UI each spelled a collection path for themselves and disagreed
by one trailing slash, which surfaced as an empty table rather than an error.
One source of path text is the only structural fix.

The paths below are graded against Tobogganing's own ``app.url_map`` by
``tests/api/test_tobogganing_allowlist.py``, which boots the product (or falls
back to the vendored table in ``tests/api/fixtures/tobogganing_source.json``).

Trailing slashes are asymmetric WITHIN this product
===================================================
Gough registers some collections with a trailing slash and some without; Nest
registers none with one. Tobogganing does **both, for two paths that both read
as "clusters"**, and every rule is ``strict_slashes=True``:

* ``GET /api/v1/clusters/``      — registered WITH the slash
  (``hub_api/api/headend_routes.py:614``). A request to ``/api/v1/clusters``
  earns a 308 the portal's transport does not follow.
* ``GET /api/v1/sdwan/clusters`` — registered WITHOUT
  (``hub_api/modules/sdwan/api/clusters.py``). A request to
  ``/api/v1/sdwan/clusters/`` earns a flat 404 with no redirect back.

Both failure modes surface to the operator as an empty table rather than an
error, so appending a slash uniformly and stripping it uniformly are both
defects — in opposite directions. The exact registered string is what the
builders emit, and the test asserts it against the real route map.

Why the allowlist contains no machine-plane route
=================================================
Tobogganing's headend control plane (``/firewall/rules``, ``/wireguard/peers``,
``/headend/{id}/ports``, ``/certs/certificates``, the DNS resolver config and
heartbeat routes) is guarded by ``@require_machine_jwt``, which rejects any
token whose ``aud`` is not ``"headend"``
(``hub_api/auth/middleware.py:516-517``). A portal connection's credential
comes from ``POST /api/v1/auth/login``, which issues ``aud =
config.product_name`` = ``"tobogganing"`` (``hub_api/auth/service.py:341``,
``hub_api/config/__init__.py:36``). No token the portal can obtain will ever
satisfy those routes, so a rule admitting one would be a guaranteed 401 dressed
up as a feature. They are named in :data:`TOBOGGANING_UNEXPOSED_ROUTES` instead,
and the check is mechanical rather than editorial:
``test_tobogganing_allowlist.py`` reads the auth class of every route out of the
product itself and asserts no allowlist rule points at a non-``user`` one.

The same applies to the node-credential routes (``POST /sdwan/clients``,
``POST /sdwan/clusters``, the rotate-key and tunnel-config routes): they
authenticate a bootstrap enrolment token or a client api_key inline rather than
by decorator, and two of them **return a freshly minted api_key in the response
body**. Proxying those would turn the portal into a credential-minting oracle.

Which mutations are proxied, and why that is allowed here
=========================================================
Unlike Nest — where every create answers ``202`` with an ``operationId``, so
every write had to be a typed method — **Tobogganing's user-reachable surface
has no asynchronous operations at all**: no handler under ``hub_api/modules/sase``,
``hub_api/modules/sdwan/api`` or ``hub_api/api`` returns ``202``. Every mutation
answers ``200``/``201`` with the resulting object.

:mod:`app.adapters.base` draws the line at "does the caller need something the
product's own response body does not already say". For these routes it does
not: there is no :class:`~app.adapters.base.Operation` to poll and no
``ActionResult`` to build, so the proxy's byte-pipe behaviour loses nothing.
The SASE authoring mutations are therefore proxied under the ``manage`` scope.

Consequently Tobogganing exposes **no operation surface**: ``list_operations``,
``get_operation``, ``cancel_operation`` and ``operation_logs`` stay unsupported
on the adapter rather than returning an empty page that would read as "nothing
running".
"""

from __future__ import annotations

from typing import Final

from ..base import ID_UUID, RouteRule, product_scope

__all__ = [
    "PRODUCT_TYPE",
    "SCOPE_READ",
    "SCOPE_MANAGE",
    "SCOPES",
    "API_PREFIX",
    "HEALTH_ENDPOINT",
    "READY_ENDPOINT",
    "PATH_CLUSTERS_FLAT",
    "PATH_SDWAN_CLIENTS",
    "PATH_SDWAN_CLUSTERS",
    "PATH_SDWAN_STATUS",
    "PATH_WIREGUARD_PEERS",
    "PATH_BLOCKPAGE_PAGES",
    "PATH_BLOCKPAGE_ROUTES",
    "PATH_SWG_POLICY",
    "PATH_SWG_CATEGORIES",
    "blockpage_path",
    "TOBOGGANING_ROUTE_ALLOWLIST",
    "TOBOGGANING_UNEXPOSED_ROUTES",
]

#: Registry key. Must match ``ADAPTER_REGISTRY``.
PRODUCT_TYPE: Final[str] = "tobogganing"

#: Per-product scopes, built with the shared helper so the spelling is defined
#: once. ``resolve_scopes`` really mints these — see the model in
#: :mod:`app.adapters.base`.
#:
#: Tobogganing's OWN middleware requires a different vocabulary of the stored
#: credential (``sase:read``, ``clusters:read``, ``clients:read``, granted as
#: the wildcards ``*:read``/``*:write`` by ``ROLE_SCOPES`` at
#: ``hub_api/auth/service.py:24-28``). That is the product's business, not the
#: portal's: nothing in the portal mints a ``tobogganing:sase:read``, so a rule
#: requiring one would answer 403 to every token the portal can issue while
#: looking more precisely secured than what it replaced.
SCOPE_READ: Final[str] = product_scope(PRODUCT_TYPE, "read")
SCOPE_MANAGE: Final[str] = product_scope(PRODUCT_TYPE, "manage")
SCOPES: Final[tuple[str, str]] = (SCOPE_READ, SCOPE_MANAGE)

#: Tobogganing mounts its whole API under this prefix.
API_PREFIX: Final[str] = "/api/v1"

#: Liveness. Tobogganing registers ``/health`` and ``/ready`` at the app root
#: and does NOT register ``/healthz`` anywhere, so the contract's default health
#: path would 404 against a real Tobogganing.
HEALTH_ENDPOINT: Final[str] = "/health"
READY_ENDPOINT: Final[str] = "/ready"

#: The flat cluster list. **The trailing slash is registered and required** —
#: see the module docstring. Never "tidy" it away.
PATH_CLUSTERS_FLAT: Final[str] = f"{API_PREFIX}/clusters/"

#: SD-WAN collections. Registered WITHOUT a trailing slash — the opposite of
#: :data:`PATH_CLUSTERS_FLAT`, which is why neither is derived from the other.
#:
#: :data:`PATH_SDWAN_STATUS` is defined but deliberately NOT allowlisted — see
#: the tenant-blindness note in :data:`TOBOGGANING_UNEXPOSED_ROUTES`.
PATH_SDWAN_CLIENTS: Final[str] = f"{API_PREFIX}/sdwan/clients"
PATH_SDWAN_CLUSTERS: Final[str] = f"{API_PREFIX}/sdwan/clusters"
PATH_SDWAN_STATUS: Final[str] = f"{API_PREFIX}/sdwan/status"

#: The WireGuard peer list a portal credential can actually read. NOT
#: ``/api/v1/wireguard/peers``, which is the identically-named machine-plane
#: route (``@require_machine_jwt("wireguard:read")``) and is refused below.
PATH_WIREGUARD_PEERS: Final[str] = f"{API_PREFIX}/sdwan/wireguard/peers"

#: SASE authoring surface.
PATH_BLOCKPAGE_PAGES: Final[str] = f"{API_PREFIX}/sase/blockpages/pages"
PATH_BLOCKPAGE_ROUTES: Final[str] = f"{API_PREFIX}/sase/blockpages/routes"
PATH_SWG_POLICY: Final[str] = f"{API_PREFIX}/sase/swg/policy"
PATH_SWG_CATEGORIES: Final[str] = f"{API_PREFIX}/sase/swg/categories"

#: Literal sub-collections beneath a block page id. Named so the allowlist's id
#: slot can never be mistaken for one of them.
SEGMENT_PREVIEW: Final[str] = "preview"
SEGMENT_PUBLISH: Final[str] = "publish"


def blockpage_path(page_id: str, *segments: str) -> str:
    """Build a block-page item path with no trailing slash.

    ``page_id`` is a real id for typed adapter methods, or the
    :data:`~app.adapters.base.ID_UUID` pattern for allowlist rules (which are
    matched before any substitution). Segments are module literals — never
    caller input.
    """
    joined = "/".join(str(segment) for segment in segments if segment != "")
    base = f"{PATH_BLOCKPAGE_PAGES}/{page_id}"
    return f"{base}/{joined}" if joined else base


#: Deny-by-default proxy allowlist.
#:
#: Reads take :data:`SCOPE_READ`; **every mutating verb takes**
#: :data:`SCOPE_MANAGE`, which ``test_adapter_registry`` enforces registry-wide.
#:
#: Block pages are named by ``str(uuid.uuid4())``
#: (``hub_api/modules/sase/security/blockpages/pages.py:41``), so
#: :data:`~app.adapters.base.ID_UUID` is the honest shape — tighter than
#: ``ID_SLUG`` and, unlike a permissive pattern, structurally incapable of
#: matching a literal sub-collection such as ``preview`` or ``publish``.
TOBOGGANING_ROUTE_ALLOWLIST: list[RouteRule] = [
    # -- liveness -------------------------------------------------------
    RouteRule("GET", rf"^{HEALTH_ENDPOINT}\Z", SCOPE_READ),
    RouteRule("GET", rf"^{READY_ENDPOINT}\Z", SCOPE_READ),
    # -- SD-WAN reads ---------------------------------------------------
    RouteRule("GET", rf"^{PATH_CLUSTERS_FLAT}\Z", SCOPE_READ),
    RouteRule("GET", rf"^{PATH_SDWAN_CLIENTS}\Z", SCOPE_READ),
    RouteRule("GET", rf"^{PATH_SDWAN_CLUSTERS}\Z", SCOPE_READ),
    RouteRule("GET", rf"^{PATH_WIREGUARD_PEERS}\Z", SCOPE_READ),
    # -- SASE reads ------------------------------------------------------
    RouteRule("GET", rf"^{PATH_BLOCKPAGE_PAGES}\Z", SCOPE_READ),
    RouteRule("GET", rf"^{PATH_BLOCKPAGE_ROUTES}\Z", SCOPE_READ),
    RouteRule("GET", rf"^{PATH_SWG_POLICY}\Z", SCOPE_READ),
    # -- SASE authoring (synchronous; nothing to poll) -------------------
    RouteRule("POST", rf"^{PATH_BLOCKPAGE_PAGES}\Z", SCOPE_MANAGE),
    RouteRule("PUT", rf"^{blockpage_path(ID_UUID)}\Z", SCOPE_MANAGE),
    RouteRule("POST", rf"^{blockpage_path(ID_UUID, SEGMENT_PREVIEW)}\Z", SCOPE_MANAGE),
    RouteRule("POST", rf"^{blockpage_path(ID_UUID, SEGMENT_PUBLISH)}\Z", SCOPE_MANAGE),
    RouteRule("PUT", rf"^{PATH_BLOCKPAGE_ROUTES}\Z", SCOPE_MANAGE),
    RouteRule("PUT", rf"^{PATH_SWG_POLICY}\Z", SCOPE_MANAGE),
    RouteRule("POST", rf"^{PATH_SWG_CATEGORIES}\Z", SCOPE_MANAGE),
]


#: Concrete requests the proxy must refuse, with a real id in place of any
#: pattern. See :attr:`app.adapters.base.Adapter.unexposed_routes` — the
#: registry's structural id checks compare a pattern only against literals THIS
#: adapter declares, so a route Tobogganing mounts and this adapter omits is
#: invisible to them and has to be named.
#:
#: Three hazard classes, all verified against a live boot of the product rather
#: than transcribed from its spec:
#:
#: 1. **The machine control plane** (``aud=="headend"``). Unreachable with a
#:    portal credential, so admitting one buys nothing and risks everything if
#:    an operator ever stores the shared ``HEADEND_API_TOKEN`` as a connection
#:    credential — the legacy dual-accept branch at ``middleware.py:587-626``
#:    would then accept it, with ``g.machine_tenant`` hardcoded to ``"default"``
#:    (``:619``), bypassing tenant scoping entirely.
#: 2. **Credential-minting node routes.** ``POST /sdwan/clients`` and
#:    ``POST /sdwan/clusters`` return a freshly generated ``api_key``;
#:    ``rotate-key`` issues a new one.
#: 3. **The token surface itself** — login, refresh, token issuance,
#:    validation, revocation and the JWT signing keys.
TOBOGGANING_UNEXPOSED_ROUTES: tuple[tuple[str, str], ...] = (
    # -- machine control plane (aud=="headend") --------------------------
    ("GET", "/api/v1/firewall/rules"),
    ("GET", "/api/v1/wireguard/peers"),
    ("GET", "/api/v1/headend/headend-1/ports"),
    ("POST", "/api/v1/certs/certificates"),
    ("GET", "/api/v1/sase/swg/radix"),
    ("GET", "/api/v1/netsvcs/dns-servers/server-1/config"),
    ("POST", "/api/v1/netsvcs/dns-servers/server-1/heartbeat"),
    ("POST", "/api/v1/sdwan/clients/headends/headend-1/metrics"),
    # -- unauthenticated AND tenant-blind ---------------------------------
    # GET /api/v1/sdwan/status carries no auth decorator at all and hardcodes
    # `tenant_id = "default"` (hub_api/modules/sdwan/api/status.py:30, comment
    # "Phase-0 uses default tenant"). It therefore reports the DEFAULT
    # tenant's cluster and client counts to whoever asks, regardless of which
    # tenant's connection is being used. Proxying it would surface one
    # tenant's fleet size inside every other tenant's portal — a cross-tenant
    # leak through a route that looks like a harmless status endpoint.
    ("GET", "/api/v1/sdwan/status"),
    # -- credential-minting / node-credential routes ---------------------
    ("POST", "/api/v1/sdwan/clients"),
    ("POST", "/api/v1/sdwan/clusters"),
    ("POST", "/api/v1/sdwan/clients/client-1/rotate-key"),
    ("PUT", "/api/v1/sdwan/clients/client-1/tunnel-config"),
    ("GET", "/api/v1/sdwan/clients/client-1/config"),
    ("GET", "/api/v1/sdwan/clusters/cluster-1/headend-config"),
    ("POST", "/api/v1/sdwan/clusters/cluster-1/heartbeat"),
    ("POST", "/api/v1/sdwan/clients/client-1/metrics"),
    ("POST", "/api/v1/netsvcs/dns-servers/register"),
    ("POST", "/api/v1/netsvcs/dns-servers/server-1/refresh-token"),
    ("POST", "/api/v1/perftest_cluster/enrollment/enroll"),
    ("GET", "/api/v1/perftest_cluster/enrollment/secrets"),
    # -- token and signing-key surface -----------------------------------
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/token"),
    ("POST", "/api/v1/auth/validate"),
    ("GET", "/api/v1/auth/public-key"),
    ("POST", "/api/v1/jwt/token"),
    ("POST", "/api/v1/jwt/refresh"),
    ("POST", "/api/v1/jwt/revoke"),
    ("POST", "/api/v1/jwt/validate"),
    ("GET", "/api/v1/jwt/public-key"),
    # -- the API map itself ----------------------------------------------
    # Serving a product's full route inventory through the portal hands an
    # attacker the enumeration step for free.
    ("GET", "/openapi.json"),
    ("GET", "/docs/public"),
)
