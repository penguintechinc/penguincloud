"""MarchProxy Adapter — API Gateway management."""

from typing import Any

from .base_adapter import ProductAdapter


class MarchProxyAdapter(ProductAdapter):
    PRODUCT_TYPE = "marchproxy"
    DISPLAY_NAME = "MarchProxy"
    CATEGORY = "infrastructure"
    ICON = "shield"
    DEFAULT_HEALTH_ENDPOINT = "/healthz"
    DEFAULT_API_VERSION = "v1"
    DISCOVERY_PORTS = [8080, 8443, 443]
    DISCOVERY_SIGNATURES = ["marchproxy", "MarchProxy"]

    def get_capabilities(self) -> list[str]:
        return ["health_check", "proxy", "services", "clusters", "certificates"]

    def get_management_schema(self) -> dict[str, Any]:
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.DISPLAY_NAME,
            "sections": [
                {"id": "overview", "label": "Overview", "type": "dashboard"},
                {"id": "services", "label": "Services", "endpoint": "/services"},
                {"id": "clusters", "label": "Clusters", "endpoint": "/clusters"},
                {
                    "id": "certificates",
                    "label": "Certificates",
                    "endpoint": "/certificates",
                },
            ],
        }
