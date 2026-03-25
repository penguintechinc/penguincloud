"""IceCharts Adapter — Visualization."""

from .base_adapter import ProductAdapter


class IceChartsAdapter(ProductAdapter):
    PRODUCT_TYPE = "icecharts"
    DISPLAY_NAME = "IceCharts"
    CATEGORY = "monitoring"
    ICON = "bar-chart"
    DEFAULT_HEALTH_ENDPOINT = "/healthz"
    DEFAULT_API_VERSION = "v1"
    DISCOVERY_PORTS = [3000, 8080]
    DISCOVERY_SIGNATURES = ["icecharts", "IceCharts"]

    def get_capabilities(self) -> list[str]:
        return ["health_check", "proxy", "charts", "dashboards"]

    def get_management_schema(self) -> dict:
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.DISPLAY_NAME,
            "sections": [
                {"id": "overview", "label": "Overview", "type": "dashboard"},
                {"id": "charts", "label": "Charts", "endpoint": "/charts"},
                {"id": "dashboards", "label": "Dashboards", "endpoint": "/dashboards"},
            ],
        }
