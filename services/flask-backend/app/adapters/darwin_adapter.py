"""Darwin Adapter — Evolution/deployment management."""

from .base_adapter import ProductAdapter


class DarwinAdapter(ProductAdapter):
    PRODUCT_TYPE = "darwin"
    DISPLAY_NAME = "Darwin"
    CATEGORY = "operations"
    ICON = "git-branch"
    DEFAULT_HEALTH_ENDPOINT = "/healthz"
    DEFAULT_API_VERSION = "v1"
    DISCOVERY_PORTS = [8080]
    DISCOVERY_SIGNATURES = ["darwin", "Darwin"]

    def get_capabilities(self) -> list[str]:
        return ["health_check", "proxy", "deployments"]

    def get_management_schema(self) -> dict:
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.DISPLAY_NAME,
            "sections": [
                {"id": "overview", "label": "Overview", "type": "dashboard"},
                {"id": "deployments", "label": "Deployments", "endpoint": "/deployments"},
            ],
        }
