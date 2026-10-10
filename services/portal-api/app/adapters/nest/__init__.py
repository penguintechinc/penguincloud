"""Nest adapter package — contract v2 against the live nest-api service."""

from __future__ import annotations

from .adapter import NestAdapter
from .mapping import (
    KIND_DATABASE,
    KIND_PROTECTION_POLICY,
    KIND_SEARCH_POOL,
    KIND_SNAPSHOT,
    OP_KIND,
    RESOURCE_KINDS,
)
from .routes import (
    NEST_ROUTE_ALLOWLIST,
    NEST_UNEXPOSED_ROUTES,
    PRODUCT_TYPE,
    SCOPES,
    tenant_path,
)

__all__ = [
    "NestAdapter",
    "NEST_ROUTE_ALLOWLIST",
    "NEST_UNEXPOSED_ROUTES",
    "PRODUCT_TYPE",
    "SCOPES",
    "tenant_path",
    "KIND_DATABASE",
    "KIND_SNAPSHOT",
    "KIND_PROTECTION_POLICY",
    "KIND_SEARCH_POOL",
    "OP_KIND",
    "RESOURCE_KINDS",
]
