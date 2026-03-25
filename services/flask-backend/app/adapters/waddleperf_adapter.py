"""WaddlePerf Adapter — Performance monitoring."""

from .base_adapter import ProductAdapter


class WaddlePerfAdapter(ProductAdapter):
    PRODUCT_TYPE = "waddleperf"
    DISPLAY_NAME = "WaddlePerf"
    CATEGORY = "monitoring"
    ICON = "activity"
    DEFAULT_HEALTH_ENDPOINT = "/healthz"
    DEFAULT_API_VERSION = "v1"
    DISCOVERY_PORTS = [8080, 9090]
    DISCOVERY_SIGNATURES = ["waddleperf", "WaddlePerf"]

    def get_capabilities(self) -> list[str]:
        return ["health_check", "proxy", "benchmarks", "reports"]

    def get_management_schema(self) -> dict:
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.DISPLAY_NAME,
            "sections": [
                {"id": "overview", "label": "Overview", "type": "dashboard"},
                {"id": "benchmarks", "label": "Benchmarks", "endpoint": "/benchmarks"},
                {"id": "reports", "label": "Reports", "endpoint": "/reports"},
            ],
        }
