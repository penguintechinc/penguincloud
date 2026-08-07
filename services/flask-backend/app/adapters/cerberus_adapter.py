"""Cerberus Adapter — Authentication/IAM."""

from typing import Any

from .base_adapter import ProductAdapter


class CerberusAdapter(ProductAdapter):
    PRODUCT_TYPE = "cerberus"
    DISPLAY_NAME = "Cerberus"
    CATEGORY = "security"
    ICON = "lock"
    DEFAULT_HEALTH_ENDPOINT = "/healthz"
    DEFAULT_API_VERSION = "v1"
    DISCOVERY_PORTS = [8080, 443]
    DISCOVERY_SIGNATURES = ["cerberus", "Cerberus"]

    def get_capabilities(self) -> list[str]:
        return ["health_check", "proxy", "policies", "sessions", "audit"]

    def get_management_schema(self) -> dict[str, Any]:
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.DISPLAY_NAME,
            "sections": [
                {"id": "overview", "label": "Overview", "type": "dashboard"},
                {"id": "policies", "label": "Policies", "endpoint": "/policies"},
                {"id": "sessions", "label": "Sessions", "endpoint": "/sessions"},
                {"id": "audit", "label": "Audit", "endpoint": "/audit"},
            ],
        }
