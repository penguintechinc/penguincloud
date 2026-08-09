"""Tobogganing adapter package — contract v2 against the live hub_api service."""

from __future__ import annotations

from .adapter import TobogganingAdapter
from .mapping import (
    COLLECTION_ENVELOPE_KEYS,
    KIND_BLOCK_PAGE,
    KIND_BLOCKPAGE_ROUTE,
    KIND_LIST_ROUTES,
    KIND_SDWAN_CLIENT,
    KIND_SDWAN_CLUSTER,
    KIND_SWG_POLICY,
    KIND_WIREGUARD_PEER,
    RESOURCE_KINDS,
    envelope_key,
)
from .routes import (
    PRODUCT_TYPE,
    SCOPES,
    TOBOGGANING_ROUTE_ALLOWLIST,
    TOBOGGANING_UNEXPOSED_ROUTES,
)

__all__ = [
    "TobogganingAdapter",
    "TOBOGGANING_ROUTE_ALLOWLIST",
    "TOBOGGANING_UNEXPOSED_ROUTES",
    "PRODUCT_TYPE",
    "SCOPES",
    "COLLECTION_ENVELOPE_KEYS",
    "KIND_LIST_ROUTES",
    "RESOURCE_KINDS",
    "envelope_key",
    "KIND_SDWAN_CLIENT",
    "KIND_SDWAN_CLUSTER",
    "KIND_WIREGUARD_PEER",
    "KIND_BLOCK_PAGE",
    "KIND_BLOCKPAGE_ROUTE",
    "KIND_SWG_POLICY",
]
