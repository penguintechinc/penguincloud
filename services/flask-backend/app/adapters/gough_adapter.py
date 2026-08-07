"""Gough Adapter — Workflow automation."""

from typing import Any

from .base_adapter import ProductAdapter


class GoughAdapter(ProductAdapter):
    PRODUCT_TYPE = "gough"
    DISPLAY_NAME = "Gough"
    CATEGORY = "operations"
    ICON = "settings"
    DEFAULT_HEALTH_ENDPOINT = "/healthz"
    DEFAULT_API_VERSION = "v1"
    DISCOVERY_PORTS = [8080]
    DISCOVERY_SIGNATURES = ["gough", "Gough"]

    def get_capabilities(self) -> list[str]:
        return ["health_check", "proxy", "workflows", "jobs"]

    def get_management_schema(self) -> dict[str, Any]:
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.DISPLAY_NAME,
            "sections": [
                {"id": "overview", "label": "Overview", "type": "dashboard"},
                {"id": "workflows", "label": "Workflows", "endpoint": "/workflows"},
                {"id": "jobs", "label": "Jobs", "endpoint": "/jobs"},
            ],
        }
