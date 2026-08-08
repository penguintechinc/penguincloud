"""SkausWatch Adapter — Security monitoring."""

from typing import Any

from .base_adapter import ProductAdapter


class SkausWatchAdapter(ProductAdapter):
    PRODUCT_TYPE = "skauswatch"
    DISPLAY_NAME = "SkausWatch"
    CATEGORY = "security"
    ICON = "eye"
    DEFAULT_HEALTH_ENDPOINT = "/healthz"
    DEFAULT_API_VERSION = "v1"
    DISCOVERY_PORTS = [9200, 5601, 8080]
    DISCOVERY_SIGNATURES = ["skauswatch", "SkausWatch"]

    def get_capabilities(self) -> list[str]:
        return ["health_check", "proxy", "alerts", "threat_intel", "edr"]

    def get_management_schema(self) -> dict[str, Any]:
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.DISPLAY_NAME,
            "sections": [
                {"id": "overview", "label": "Overview", "type": "dashboard"},
                {"id": "alerts", "label": "Alerts", "endpoint": "/alerts"},
                {
                    "id": "threat_intel",
                    "label": "Threat Intel",
                    "endpoint": "/threat-intel",
                },
                {"id": "edr", "label": "EDR", "endpoint": "/edr"},
            ],
        }
