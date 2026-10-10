"""WaddleAI adapter package — Phase 8 acceptance test, read-only cut."""

from __future__ import annotations

from .adapter import WaddleAIAdapter
from .mapping import (
    COLLECTION_ENVELOPE_KEYS,
    KIND_KNOWLEDGE_DOCUMENT,
    KIND_LIST_ROUTES,
    KIND_PROVIDER,
    KIND_QUOTA,
    RESOURCE_KINDS,
    envelope_key,
)
from .routes import (
    PRODUCT_TYPE,
    SCOPES,
    WADDLEAI_ROUTE_ALLOWLIST,
    WADDLEAI_UNEXPOSED_ROUTES,
)

__all__ = [
    "WaddleAIAdapter",
    "WADDLEAI_ROUTE_ALLOWLIST",
    "WADDLEAI_UNEXPOSED_ROUTES",
    "PRODUCT_TYPE",
    "SCOPES",
    "COLLECTION_ENVELOPE_KEYS",
    "KIND_LIST_ROUTES",
    "RESOURCE_KINDS",
    "envelope_key",
    "KIND_PROVIDER",
    "KIND_KNOWLEDGE_DOCUMENT",
    "KIND_QUOTA",
]
