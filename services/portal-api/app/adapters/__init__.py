"""Product adapter registry — v2 contract.

Two tiers, deliberately distinguished in the API surface:

* **Active** — a product with a real v2 adapter. It can be connected,
  health-checked, and proxied to within its declared ``route_allowlist``.
* **Planned** — a product the portal knows the name of and nothing else.
  It appears in the catalogue with ``status: planned`` so the UI can show a
  roadmap, but :func:`get_adapter` refuses it, which means no connection to
  a planned product can be created, health-checked, or proxied.

Phase 3 deleted the seventeen thin metadata adapters that used to back the
planned tier. Each was ~40 lines of blocking ``requests`` calls and
hand-rolled auth headers behind an interface no caller could rely on: they
implemented different subsets of the old base class, so "the adapter exists"
told you nothing about what would happen when you called it. Keeping them as
registry *metadata* preserves everything they actually provided (a name and
a category for the catalogue) and removes the implication that the portal
can manage a product it cannot.
"""

from __future__ import annotations

from typing import Any, Final

from .base import Adapter, AdapterContext
from .generic_adapter import GenericAdapter
from .gough import GoughAdapter
from .gough.manifest import GOUGH_MANIFEST
from .manifest import ConsoleManifest
from .nest import NestAdapter
from .tobogganing import TobogganingAdapter

__all__ = [
    "ADAPTER_REGISTRY",
    "MANIFEST_REGISTRY",
    "PLANNED_PRODUCTS",
    "STATUS_ACTIVE",
    "STATUS_PLANNED",
    "get_adapter",
    "get_adapter_metadata",
    "get_all_product_types",
]

STATUS_ACTIVE: Final[str] = "active"
STATUS_PLANNED: Final[str] = "planned"
STATUS_UNKNOWN: Final[str] = "unknown"

#: product_type -> v2 adapter class. Membership here is what makes a product
#: connectable; everything else is catalogue metadata.
ADAPTER_REGISTRY: dict[str, type[Adapter]] = {
    "gough": GoughAdapter,
    "nest": NestAdapter,
    "tobogganing": TobogganingAdapter,
    # Health-only fallback with an empty proxy allowlist. Present so an
    # operator can register and monitor an endpoint the portal has no
    # specific integration for, without that endpoint becoming proxyable.
    "generic": GenericAdapter,
}

#: product_type -> committed console manifest — Design §3, Approach B.
#:
#: Deliberately a SEPARATE, smaller registry than :data:`ADAPTER_REGISTRY`
#: rather than an optional attribute bolted onto it: an active adapter with
#: no manifest entry here is a product the typed proxy/adapter surface
#: supports but the declarative console does not yet describe — a real,
#: expected state during migration (Design §7), not an error. Importing
#: ``gough.manifest`` here (rather than lazily, on first request) is what
#: makes an invalid manifest a deployment-time import failure instead of a
#: first-request one — see that module's own fail-closed
#: ``validate_manifest`` call at the bottom of the file.
MANIFEST_REGISTRY: dict[str, ConsoleManifest] = {
    "gough": GOUGH_MANIFEST,
}

#: Products with no adapter. Catalogue entries only — get_adapter() raises
#: for every key in here, so a connection to one cannot be exercised.
PLANNED_PRODUCTS: Final[dict[str, dict[str, str]]] = {
    "marchproxy": {"display_name": "MarchProxy", "category": "networking"},
    "squawk": {"display_name": "Squawk", "category": "dns"},
    "license_server": {"display_name": "License Server", "category": "licensing"},
    "skauswatch": {"display_name": "SkausWatch", "category": "monitoring"},
    "waddleai": {"display_name": "WaddleAI", "category": "ai"},
    "articdbm": {"display_name": "ArticDBM", "category": "database"},
    "cerberus": {"display_name": "Cerberus", "category": "security"},
    "waddlebot": {"display_name": "Waddles", "category": "community"},
    "waddleperf": {"display_name": "WaddlePerf", "category": "monitoring"},
    "iceshelves": {"display_name": "IceShelves", "category": "storage"},
    "icecharts": {"display_name": "IceCharts", "category": "analytics"},
    "killkrill": {"display_name": "KillKrill", "category": "logging"},
    "darwin": {"display_name": "Darwin", "category": "security"},
    "current": {"display_name": "Current", "category": "networking"},
    "elder": {"display_name": "Elder", "category": "crm"},
    "admin": {"display_name": "Admin", "category": "admin"},
}


def get_adapter(product_type: str, ctx: AdapterContext) -> Adapter:
    """Instantiate the adapter for a product type.

    Args:
        product_type: Registry key, e.g. ``"gough"``.
        ctx: Context for the call. Held by the caller rather than the
            adapter instance — adapters are stateless and take ``ctx`` per
            method, so one cannot accidentally retain another tenant's
            credentials between requests.

    Raises:
        ValueError: The product type has no adapter. Planned products land
            here too: the catalogue lists them, but nothing may be executed
            against them.
    """
    adapter_class = ADAPTER_REGISTRY.get(product_type)
    if adapter_class is None:
        raise ValueError(
            f"Product '{product_type}' has no adapter " f"(active: {sorted(ADAPTER_REGISTRY)})"
        )
    return adapter_class()


def get_adapter_metadata(product_type: str) -> dict[str, Any]:
    """Return catalogue metadata for one product type."""
    adapter_class = ADAPTER_REGISTRY.get(product_type)
    if adapter_class is not None:
        return {
            "product_type": product_type,
            "display_name": getattr(adapter_class, "DISPLAY_NAME", product_type),
            "status": STATUS_ACTIVE,
        }

    planned = PLANNED_PRODUCTS.get(product_type)
    if planned is not None:
        return {
            "product_type": product_type,
            "display_name": planned["display_name"],
            "category": planned["category"],
            "status": STATUS_PLANNED,
        }

    return {
        "product_type": product_type,
        "display_name": product_type,
        "status": STATUS_UNKNOWN,
    }


def get_all_product_types() -> list[dict[str, Any]]:
    """Return the full catalogue: active adapters plus planned products."""
    catalogue = [
        {
            "product_type": ptype,
            "display_name": getattr(cls, "DISPLAY_NAME", ptype),
            "status": STATUS_ACTIVE,
        }
        for ptype, cls in ADAPTER_REGISTRY.items()
    ]
    catalogue.extend(
        {
            "product_type": ptype,
            "display_name": meta["display_name"],
            "category": meta.get("category", "other"),
            "status": STATUS_PLANNED,
        }
        for ptype, meta in PLANNED_PRODUCTS.items()
    )
    return sorted(catalogue, key=lambda entry: (entry["status"], entry["display_name"]))
