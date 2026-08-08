"""Generic Product Adapter — fallback for unknown product types."""

from typing import Any

from .base_adapter import ProductAdapter


class GenericAdapter(ProductAdapter):
    """Fallback adapter for unrecognized products. Provides raw proxy passthrough."""

    PRODUCT_TYPE = "generic"
    DISPLAY_NAME = "Generic Product"
    CATEGORY = "operations"
    ICON = "package"
    DEFAULT_HEALTH_ENDPOINT = "/healthz"
    DEFAULT_API_VERSION = "v1"
    DISCOVERY_PORTS: list[int] = []
    DISCOVERY_SIGNATURES: list[str] = []

    def get_management_schema(self) -> dict[str, Any]:
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.connection.get("display_name", "Unknown Product"),
            "sections": [
                {
                    "id": "overview",
                    "label": "Overview",
                    "type": "health_summary",
                },
            ],
        }
