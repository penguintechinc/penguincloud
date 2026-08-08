"""Elder Adapter — Legacy services."""

from typing import Any

from .base_adapter import ProductAdapter


class ElderAdapter(ProductAdapter):
    PRODUCT_TYPE = "elder"
    DISPLAY_NAME = "Elder"
    CATEGORY = "legacy"
    ICON = "archive"
    DEFAULT_HEALTH_ENDPOINT = "/healthz"
    DEFAULT_API_VERSION = "v1"
    DISCOVERY_PORTS = [8080]
    DISCOVERY_SIGNATURES = ["elder", "Elder"]

    def get_capabilities(self) -> list[str]:
        return ["health_check", "proxy", "services"]

    def get_management_schema(self) -> dict[str, Any]:
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.DISPLAY_NAME,
            "sections": [
                {"id": "overview", "label": "Overview", "type": "dashboard"},
                {"id": "services", "label": "Services", "endpoint": "/services"},
            ],
        }
