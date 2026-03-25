"""WaddleAI Adapter — AI/ML platform."""

from .base_adapter import ProductAdapter


class WaddleAIAdapter(ProductAdapter):
    PRODUCT_TYPE = "waddleai"
    DISPLAY_NAME = "WaddleAI"
    CATEGORY = "ai"
    ICON = "brain"
    DEFAULT_HEALTH_ENDPOINT = "/healthz"
    DEFAULT_API_VERSION = "v1"
    DISCOVERY_PORTS = [8080, 11434]
    DISCOVERY_SIGNATURES = ["waddleai", "WaddleAI"]

    def get_capabilities(self) -> list[str]:
        return ["health_check", "proxy", "api_keys", "models", "usage"]

    def get_management_schema(self) -> dict:
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.DISPLAY_NAME,
            "sections": [
                {"id": "overview", "label": "Overview", "type": "dashboard"},
                {"id": "api_keys", "label": "API Keys", "endpoint": "/keys"},
                {"id": "models", "label": "Models", "endpoint": "/models"},
                {"id": "usage", "label": "Usage", "endpoint": "/usage"},
            ],
        }
