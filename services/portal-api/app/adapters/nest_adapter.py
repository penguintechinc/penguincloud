"""Nest Adapter — v2 Stub (Phase 4 implementation).

Data and database management product. Phase 3 provides health + capabilities
only; full CRUD operations deferred to Phase 4.
"""

from __future__ import annotations

from typing import Any

from .base import (
    AdapterCapabilityError,
    AdapterContext,
    HealthResult,
    Page,
    Resource,
    RouteRule,
)
from .transport import get_transport

__all__ = ["NestAdapter"]


class NestAdapter:
    """Nest database management adapter (Phase 3 stub)."""

    PRODUCT_TYPE: str = "nest"
    DISPLAY_NAME: str = "Nest"

    #: Declarative proxy allowlist — deny everything else
    route_allowlist: list[RouteRule] = [
        RouteRule("GET", r"^/health(z)?$", "products:read"),
        RouteRule("GET", r"^/capabilities$", "products:read"),
    ]

    async def health(self, ctx: AdapterContext) -> HealthResult:
        """Check Nest health."""
        transport = await get_transport()
        return await transport.health_check(ctx.base_url, "/healthz", ctx)

    async def capabilities(self, ctx: AdapterContext) -> list[str]:
        """List capabilities (stub: health only)."""
        return ["health"]

    async def list_resources(
        self,
        kind: str,
        ctx: AdapterContext,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Page[Resource]:
        """Not implemented in Phase 3."""
        msg = (
            f"list_resources({kind}) not implemented in "
            f"Phase 3 for {self.PRODUCT_TYPE}"
        )
        raise AdapterCapabilityError(msg)

    async def get_resource(
        self, kind: str, resource_id: str, ctx: AdapterContext
    ) -> Resource:
        """Not implemented in Phase 3."""
        msg = (
            f"get_resource({kind}) not implemented in "
            f"Phase 3 for {self.PRODUCT_TYPE}"
        )
        raise AdapterCapabilityError(msg)

    async def create_resource(
        self, kind: str, payload: dict[str, Any], ctx: AdapterContext
    ) -> Resource:
        """Not implemented in Phase 3."""
        msg = (
            f"create_resource({kind}) not implemented in "
            f"Phase 3 for {self.PRODUCT_TYPE}"
        )
        raise AdapterCapabilityError(msg)

    async def update_resource(
        self, kind: str, resource_id: str, payload: dict[str, Any], ctx: AdapterContext
    ) -> Resource:
        """Not implemented in Phase 3."""
        msg = (
            f"update_resource({kind}) not implemented in "
            f"Phase 3 for {self.PRODUCT_TYPE}"
        )
        raise AdapterCapabilityError(msg)

    async def delete_resource(
        self, kind: str, resource_id: str, ctx: AdapterContext
    ) -> None:
        """Not implemented in Phase 3."""
        msg = (
            f"delete_resource({kind}) not implemented in "
            f"Phase 3 for {self.PRODUCT_TYPE}"
        )
        raise AdapterCapabilityError(msg)

    async def metrics_summary(self, ctx: AdapterContext) -> dict[str, Any]:
        """Not implemented in Phase 3."""
        msg = (
            f"metrics_summary() not implemented in "
            f"Phase 3 for {self.PRODUCT_TYPE}"
        )
        raise AdapterCapabilityError(msg)

    async def list_users(
        self, ctx: AdapterContext, page: int = 1, per_page: int = 20
    ) -> Page[dict[str, Any]]:
        """Not implemented in Phase 3."""
        msg = (
            f"list_users() not implemented in "
            f"Phase 3 for {self.PRODUCT_TYPE}"
        )
        raise AdapterCapabilityError(msg)

    async def invite_user(
        self, payload: dict[str, Any], ctx: AdapterContext
    ) -> dict[str, Any]:
        """Not implemented in Phase 3."""
        msg = (
            f"invite_user() not implemented in "
            f"Phase 3 for {self.PRODUCT_TYPE}"
        )
        raise AdapterCapabilityError(msg)
