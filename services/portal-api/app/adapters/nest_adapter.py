"""Nest Adapter — Development environments."""

from typing import Any

from .base_adapter import ProductAdapter


class NestAdapter(ProductAdapter):
    PRODUCT_TYPE = "nest"
    DISPLAY_NAME = "Nest"
    CATEGORY = "development"
    ICON = "code"
    DEFAULT_HEALTH_ENDPOINT = "/healthz"
    DEFAULT_API_VERSION = "v1"
    DISCOVERY_PORTS = [8080, 3000]
    DISCOVERY_SIGNATURES = ["nest", "Nest"]

    def get_capabilities(self) -> list[str]:
        return ["health_check", "proxy", "environments", "templates"]

    def get_management_schema(self) -> dict[str, Any]:
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.DISPLAY_NAME,
            "sections": [
                {"id": "overview", "label": "Overview", "type": "dashboard"},
                {
                    "id": "environments",
                    "label": "Environments",
                    "endpoint": "/environments",
                },
                {"id": "templates", "label": "Templates", "endpoint": "/templates"},
            ],
        }
