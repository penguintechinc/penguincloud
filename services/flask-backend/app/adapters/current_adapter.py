"""Current Adapter — State management."""

from .base_adapter import ProductAdapter


class CurrentAdapter(ProductAdapter):
    PRODUCT_TYPE = "current"
    DISPLAY_NAME = "Current"
    CATEGORY = "operations"
    ICON = "zap"
    DEFAULT_HEALTH_ENDPOINT = "/healthz"
    DEFAULT_API_VERSION = "v1"
    DISCOVERY_PORTS = [8080]
    DISCOVERY_SIGNATURES = ["current", "Current"]

    def get_capabilities(self) -> list[str]:
        return ["health_check", "proxy", "state"]

    def get_management_schema(self) -> dict:
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.DISPLAY_NAME,
            "sections": [
                {"id": "overview", "label": "Overview", "type": "dashboard"},
                {"id": "state", "label": "State", "endpoint": "/state"},
            ],
        }
