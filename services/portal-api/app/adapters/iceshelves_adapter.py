"""IceShelves Adapter — Storage management."""

from typing import Any

from .base_adapter import ProductAdapter


class IceShelvesAdapter(ProductAdapter):
    PRODUCT_TYPE = "iceshelves"
    DISPLAY_NAME = "IceShelves"
    CATEGORY = "infrastructure"
    ICON = "hard-drive"
    DEFAULT_HEALTH_ENDPOINT = "/healthz"
    DEFAULT_API_VERSION = "v1"
    DISCOVERY_PORTS = [9000, 8080]
    DISCOVERY_SIGNATURES = ["iceshelves", "IceShelves"]

    def get_capabilities(self) -> list[str]:
        return ["health_check", "proxy", "buckets", "volumes"]

    def get_management_schema(self) -> dict[str, Any]:
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.DISPLAY_NAME,
            "sections": [
                {"id": "overview", "label": "Overview", "type": "dashboard"},
                {"id": "buckets", "label": "Buckets", "endpoint": "/buckets"},
                {"id": "volumes", "label": "Volumes", "endpoint": "/volumes"},
            ],
        }
