"""ArticDBM Adapter — Database management."""

from typing import Any

from .base_adapter import ProductAdapter


class ArticDBMAdapter(ProductAdapter):
    PRODUCT_TYPE = "articdbm"
    DISPLAY_NAME = "ArticDBM"
    CATEGORY = "infrastructure"
    ICON = "database"
    DEFAULT_HEALTH_ENDPOINT = "/healthz"
    DEFAULT_API_VERSION = "v1"
    DISCOVERY_PORTS = [8080, 3306, 5432]
    DISCOVERY_SIGNATURES = ["articdbm", "ArticDBM"]

    def get_capabilities(self) -> list[str]:
        return ["health_check", "proxy", "databases", "clusters", "backups"]

    def get_management_schema(self) -> dict[str, Any]:
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.DISPLAY_NAME,
            "sections": [
                {"id": "overview", "label": "Overview", "type": "dashboard"},
                {"id": "databases", "label": "Databases", "endpoint": "/databases"},
                {"id": "clusters", "label": "Clusters", "endpoint": "/clusters"},
                {"id": "backups", "label": "Backups", "endpoint": "/backups"},
            ],
        }
