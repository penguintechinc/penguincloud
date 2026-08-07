"""WaddleBot Adapter — Bot automation."""

from typing import Any

from .base_adapter import ProductAdapter


class WaddleBotAdapter(ProductAdapter):
    PRODUCT_TYPE = "waddlebot"
    DISPLAY_NAME = "WaddleBot"
    CATEGORY = "ai"
    ICON = "bot"
    DEFAULT_HEALTH_ENDPOINT = "/healthz"
    DEFAULT_API_VERSION = "v1"
    DISCOVERY_PORTS = [8080, 3000]
    DISCOVERY_SIGNATURES = ["waddlebot", "WaddleBot"]

    def get_capabilities(self) -> list[str]:
        return ["health_check", "proxy", "bots", "labels", "channels"]

    def get_management_schema(self) -> dict[str, Any]:
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.DISPLAY_NAME,
            "sections": [
                {"id": "overview", "label": "Overview", "type": "dashboard"},
                {"id": "bots", "label": "Bots", "endpoint": "/router"},
                {"id": "labels", "label": "Labels", "endpoint": "/labels"},
                {"id": "channels", "label": "Channels", "endpoint": "/channels"},
            ],
        }
