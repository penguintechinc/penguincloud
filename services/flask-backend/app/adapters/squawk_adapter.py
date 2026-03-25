"""Squawk Adapter — DNS management."""

from .base_adapter import ProductAdapter


class SquawkAdapter(ProductAdapter):
    PRODUCT_TYPE = "squawk"
    DISPLAY_NAME = "Squawk"
    CATEGORY = "infrastructure"
    ICON = "globe"
    DEFAULT_HEALTH_ENDPOINT = "/healthz"
    DEFAULT_API_VERSION = "v1"
    DISCOVERY_PORTS = [5380, 8053]
    DISCOVERY_SIGNATURES = ["squawk", "Squawk DNS"]

    def get_capabilities(self) -> list[str]:
        return ["health_check", "proxy", "domains", "queries", "ioc_feeds"]

    def get_management_schema(self) -> dict:
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.DISPLAY_NAME,
            "sections": [
                {"id": "overview", "label": "Overview", "type": "dashboard"},
                {"id": "domains", "label": "Domains", "endpoint": "/domains"},
                {"id": "queries", "label": "Queries", "endpoint": "/queries"},
                {"id": "ioc_feeds", "label": "IOC Feeds", "endpoint": "/ioc/feeds"},
            ],
        }
