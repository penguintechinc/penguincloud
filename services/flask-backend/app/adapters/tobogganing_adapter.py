"""Tobogganing Adapter — Deployment management."""

from .base_adapter import ProductAdapter


class TobogganingAdapter(ProductAdapter):
    PRODUCT_TYPE = "tobogganing"
    DISPLAY_NAME = "Tobogganing"
    CATEGORY = "operations"
    ICON = "rocket"
    DEFAULT_HEALTH_ENDPOINT = "/healthz"
    DEFAULT_API_VERSION = "v1"
    DISCOVERY_PORTS = [8080, 9090]
    DISCOVERY_SIGNATURES = ["tobogganing", "Tobogganing"]

    def get_capabilities(self) -> list[str]:
        return ["health_check", "proxy", "rollouts", "pipelines"]

    def get_management_schema(self) -> dict:
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.DISPLAY_NAME,
            "sections": [
                {"id": "overview", "label": "Overview", "type": "dashboard"},
                {"id": "rollouts", "label": "Rollouts", "endpoint": "/rollouts"},
                {"id": "pipelines", "label": "Pipelines", "endpoint": "/pipelines"},
            ],
        }
