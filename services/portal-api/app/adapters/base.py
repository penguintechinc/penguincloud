"""Adapter Contract v2 — Typed async Protocol and base implementation.

All adapters implement these interfaces. Transport is abstracted to a
shared httpx-based client in transport.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar

__all__ = [
    "HealthResult",
    "Resource",
    "Page",
    "AdapterContext",
    "RouteRule",
    "RBACEnforcer",
    "AdapterCapabilityError",
    "Adapter",
]


@dataclass(slots=True)
class HealthResult:
    """Health check result from an adapter."""

    status: str  # healthy, degraded, unhealthy
    status_code: int
    response_time_ms: int
    error: str | None = None


@dataclass(slots=True)
class Resource:
    """Generic resource returned by adapter."""

    id: str
    kind: str
    name: str
    metadata: dict[str, Any] = field(default_factory=dict)


T = TypeVar("T")


@dataclass(slots=True)
class Page(Generic[T]):
    """Paginated response."""

    items: list[T]
    total: int
    page: int
    per_page: int


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


@dataclass(slots=True, frozen=True)
class RouteRule:
    """Declarative proxy allowlist rule.

    One rule per endpoint; method, path pattern, and required scope(s).
    """

    method: str  # GET, POST, PUT, DELETE, PATCH
    path_regex: str  # e.g., r'^/users(/.*)?$', r'^/health$'
    required_scope: str  # e.g., 'products:read', 'products:manage'

    def matches(self, method: str, path: str) -> bool:
        """True if this rule allows the request."""
        if self.method.upper() != method.upper():
            return False
        return bool(re.match(self.path_regex, path))


class AdapterCapabilityError(Exception):
    """Raised when an adapter does not support a requested operation."""

    pass


class Adapter(Protocol):
    """Protocol all adapters must implement.

    Adapters are instantiated per-request with AdapterContext carrying
    credentials, tenant mapping, and scopes. All methods are async.
    """

    #: Declarative allowlist of routes this adapter exposes to the proxy.
    #: Each rule specifies method, path pattern, and required scope.
    route_allowlist: list[RouteRule]

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
    ) -> Page[Resource]:
        """List resources of a given kind.

        Raise AdapterCapabilityError if kind is not supported.
        """
        ...

    async def get_resource(
        self, kind: str, resource_id: str, ctx: AdapterContext
    ) -> Resource:
        """Get a single resource by kind and ID.

        Raise AdapterCapabilityError if kind is not supported.
        """
        ...

    async def create_resource(
        self, kind: str, payload: dict[str, Any], ctx: AdapterContext
    ) -> Resource:
        """Create a resource of a given kind.

        Raise AdapterCapabilityError if kind or operation is not supported.
        """
        ...

    async def update_resource(
        self, kind: str, resource_id: str, payload: dict[str, Any], ctx: AdapterContext
    ) -> Resource:
        """Update a resource of a given kind.

        Raise AdapterCapabilityError if kind or operation is not supported.
        """
        ...

    async def delete_resource(
        self, kind: str, resource_id: str, ctx: AdapterContext
    ) -> None:
        """Delete a resource of a given kind.

        Raise AdapterCapabilityError if kind or operation is not supported.
        """
        ...

    async def metrics_summary(self, ctx: AdapterContext) -> dict[str, Any]:
        """Return a metrics summary for the adapter.

        E.g., resource counts, usage stats. Raise AdapterCapabilityError if
        the adapter does not expose metrics.
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
