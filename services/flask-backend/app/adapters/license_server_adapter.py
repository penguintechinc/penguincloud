"""License Server Adapter — License management."""

from .base_adapter import ProductAdapter


class LicenseServerAdapter(ProductAdapter):
    PRODUCT_TYPE = "license_server"
    DISPLAY_NAME = "License Server"
    CATEGORY = "operations"
    ICON = "key"
    DEFAULT_HEALTH_ENDPOINT = "/healthz"
    DEFAULT_API_VERSION = "v2"
    DISCOVERY_PORTS = [8080, 443]
    DISCOVERY_SIGNATURES = ["license-server", "PenguinTech License"]

    def get_capabilities(self) -> list[str]:
        return ["health_check", "proxy", "licenses", "products", "organizations"]

    def get_management_schema(self) -> dict:
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.DISPLAY_NAME,
            "sections": [
                {"id": "overview", "label": "Overview", "type": "dashboard"},
                {"id": "licenses", "label": "Licenses", "endpoint": "/validate"},
                {"id": "products", "label": "Products", "endpoint": "/products"},
                {"id": "organizations", "label": "Organizations", "endpoint": "/organizations"},
            ],
        }
