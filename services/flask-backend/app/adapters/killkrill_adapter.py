"""KillKrill Adapter — Resource cleanup."""

from .base_adapter import ProductAdapter


class KillKrillAdapter(ProductAdapter):
    PRODUCT_TYPE = "killkrill"
    DISPLAY_NAME = "KillKrill"
    CATEGORY = "operations"
    ICON = "trash-2"
    DEFAULT_HEALTH_ENDPOINT = "/healthz"
    DEFAULT_API_VERSION = "v1"
    DISCOVERY_PORTS = [8081, 8080]
    DISCOVERY_SIGNATURES = ["killkrill", "KillKrill"]

    def get_capabilities(self) -> list[str]:
        return ["health_check", "proxy", "resources", "schedules"]

    def get_management_schema(self) -> dict:
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.DISPLAY_NAME,
            "sections": [
                {"id": "overview", "label": "Overview", "type": "dashboard"},
                {"id": "resources", "label": "Resources", "endpoint": "/resources"},
                {"id": "schedules", "label": "Schedules", "endpoint": "/schedules"},
            ],
        }
