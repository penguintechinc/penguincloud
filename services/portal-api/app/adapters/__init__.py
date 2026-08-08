"""Product Adapter Registry — v2 Contract.

Phase 3: Core adapters (gough, nest, tobogganing) implement the v2 Adapter
protocol; thin adapters are deprecated and marked as planned.
"""

from __future__ import annotations

from typing import Any, Type

from .base import Adapter, AdapterContext
from .gough_adapter import GoughAdapter
from .nest_adapter import NestAdapter
from .tobogganing_adapter import TobogganingAdapter

__all__ = ["get_adapter", "get_adapter_metadata", "get_all_product_types"]

#: Adapter registry — product_type string -> v2 Adapter class.
#: Phase 3 includes only the three core products; thin adapters are
#: deprecated and marked status:planned in the portal UI.
ADAPTER_REGISTRY: dict[str, Type[Adapter]] = {
    "gough": GoughAdapter,
    "nest": NestAdapter,
    "tobogganing": TobogganingAdapter,
}

#: Product metadata for planning/deprecated products.
#: These products are no longer actively developed but appear in the portal
#: with status:planned to show that connections may be created but will
#: have limited functionality.
PLANNED_PRODUCTS = {
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
    """Get an adapter instance for the given product type.

    Args:
        product_type: The product type string (e.g., 'gough')
        ctx: AdapterContext with connection details and credentials

    Returns:
        An instance of the adapter

    Raises:
        ValueError: If product_type is not in the active registry
    """
    adapter_class = ADAPTER_REGISTRY.get(product_type)
    if adapter_class is None:
        raise ValueError(
            f"Product {product_type} is not supported or is marked as planned. "
            f"Active products: {sorted(ADAPTER_REGISTRY.keys())}"
        )
    return adapter_class()


def get_adapter_metadata(product_type: str) -> dict[str, Any]:
    """Get metadata for a product type.

    For active products, returns v2 adapter metadata.
    For planned products, returns minimal metadata with status:planned.
    """
    if product_type in ADAPTER_REGISTRY:
        adapter_class = ADAPTER_REGISTRY[product_type]
        # Instantiate to get class attributes
        display_name = getattr(adapter_class, "DISPLAY_NAME", product_type)
        return {
            "product_type": product_type,
            "display_name": display_name,
            "status": "active",
        }

    if product_type in PLANNED_PRODUCTS:
        meta = PLANNED_PRODUCTS[product_type]
        return {
            "product_type": product_type,
            "display_name": meta["display_name"],
            "category": meta["category"],
            "status": "planned",
        }

    return {
        "product_type": product_type,
        "display_name": product_type,
        "status": "unknown",
    }


def get_all_product_types() -> list[dict[str, Any]]:
    """Get metadata for all product types (active + planned).

    Active products have full v2 adapter implementation.
    Planned products are available for connection but limited to basic ops.
    """
    result = []

    # Active products
    for ptype, cls in ADAPTER_REGISTRY.items():
        display_name = getattr(cls, "DISPLAY_NAME", ptype)
        result.append(
            {
                "product_type": ptype,
                "display_name": display_name,
                "status": "active",
            }
        )

    # Planned products
    for ptype, meta in PLANNED_PRODUCTS.items():
        result.append(
            {
                "product_type": ptype,
                "display_name": meta["display_name"],
                "category": meta.get("category", "other"),
                "status": "planned",
            }
        )

    return sorted(result, key=lambda x: (x["status"], x["display_name"]))
