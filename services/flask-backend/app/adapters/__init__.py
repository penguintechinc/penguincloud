"""Product Adapter Registry."""

from .base_adapter import ProductAdapter
from .generic_adapter import GenericAdapter
from .marchproxy_adapter import MarchProxyAdapter
from .squawk_adapter import SquawkAdapter
from .license_server_adapter import LicenseServerAdapter
from .skauswatch_adapter import SkausWatchAdapter
from .waddleai_adapter import WaddleAIAdapter
from .articdbm_adapter import ArticDBMAdapter
from .cerberus_adapter import CerberusAdapter
from .waddlebot_adapter import WaddleBotAdapter
from .waddleperf_adapter import WaddlePerfAdapter
from .iceshelves_adapter import IceShelvesAdapter
from .icecharts_adapter import IceChartsAdapter
from .killkrill_adapter import KillKrillAdapter
from .tobogganing_adapter import TobogganingAdapter
from .nest_adapter import NestAdapter
from .darwin_adapter import DarwinAdapter
from .gough_adapter import GoughAdapter
from .current_adapter import CurrentAdapter
from .elder_adapter import ElderAdapter
from .admin_adapter import AdminAdapter

# Registry mapping product_type string -> adapter class
ADAPTER_REGISTRY: dict[str, type[ProductAdapter]] = {
    "marchproxy": MarchProxyAdapter,
    "squawk": SquawkAdapter,
    "license_server": LicenseServerAdapter,
    "skauswatch": SkausWatchAdapter,
    "waddleai": WaddleAIAdapter,
    "articdbm": ArticDBMAdapter,
    "cerberus": CerberusAdapter,
    "waddlebot": WaddleBotAdapter,
    "waddleperf": WaddlePerfAdapter,
    "iceshelves": IceShelvesAdapter,
    "icecharts": IceChartsAdapter,
    "killkrill": KillKrillAdapter,
    "tobogganing": TobogganingAdapter,
    "nest": NestAdapter,
    "darwin": DarwinAdapter,
    "gough": GoughAdapter,
    "current": CurrentAdapter,
    "elder": ElderAdapter,
    "admin": AdminAdapter,
    "generic": GenericAdapter,
}


def get_adapter(product_type: str, connection: dict) -> ProductAdapter:
    """Get an adapter instance for the given product type and connection."""
    adapter_class = ADAPTER_REGISTRY.get(product_type, GenericAdapter)
    return adapter_class(connection)


def get_adapter_metadata(product_type: str) -> dict:
    """Get metadata for a product type without a connection."""
    adapter_class = ADAPTER_REGISTRY.get(product_type, GenericAdapter)
    return {
        "product_type": adapter_class.PRODUCT_TYPE,
        "display_name": adapter_class.DISPLAY_NAME,
        "category": adapter_class.CATEGORY,
        "icon": adapter_class.ICON,
        "default_health_endpoint": adapter_class.DEFAULT_HEALTH_ENDPOINT,
        "default_api_version": adapter_class.DEFAULT_API_VERSION,
        "discovery_ports": adapter_class.DISCOVERY_PORTS,
    }


def get_all_product_types() -> list[dict]:
    """Get metadata for all registered product types."""
    result = []
    for ptype, cls in ADAPTER_REGISTRY.items():
        if ptype == "generic":
            continue
        result.append({
            "product_type": cls.PRODUCT_TYPE,
            "display_name": cls.DISPLAY_NAME,
            "category": cls.CATEGORY,
            "icon": cls.ICON,
            "default_health_endpoint": cls.DEFAULT_HEALTH_ENDPOINT,
            "default_api_version": cls.DEFAULT_API_VERSION,
            "discovery_ports": cls.DISCOVERY_PORTS,
        })
    return sorted(result, key=lambda x: (x["category"], x["display_name"]))
