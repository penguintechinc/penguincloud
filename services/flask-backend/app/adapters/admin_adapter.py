"""Admin Adapter — Administration tools."""

from .base_adapter import ProductAdapter


class AdminAdapter(ProductAdapter):
    PRODUCT_TYPE = "admin"
    DISPLAY_NAME = "Admin"
    CATEGORY = "administration"
    ICON = "tool"
    DEFAULT_HEALTH_ENDPOINT = "/healthz"
    DEFAULT_API_VERSION = "v1"
    DISCOVERY_PORTS = [8080]
    DISCOVERY_SIGNATURES = ["admin", "Admin"]

    def get_capabilities(self) -> list[str]:
        return ["health_check", "proxy", "tools"]

    def get_management_schema(self) -> dict:
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.DISPLAY_NAME,
            "sections": [
                {"id": "overview", "label": "Overview", "type": "dashboard"},
                {"id": "tools", "label": "Tools", "endpoint": "/tools"},
            ],
        }
