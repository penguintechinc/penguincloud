"""PenguinTech License Server Integration."""

import logging
import os
import time
from datetime import datetime
from functools import wraps
from typing import Any, Dict, Optional

import requests
from flask import jsonify

logger = logging.getLogger(__name__)


class FeatureNotEntitledException(Exception):
    """Exception raised when feature is not entitled."""

    pass


class LicenseManager:
    """Singleton license manager for PenguinTech License Server."""

    _instance = None
    _lock = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize license manager."""
        if not hasattr(self, "_initialized"):
            self.license_key = os.getenv("LICENSE_KEY", "")
            self.server_url = os.getenv(
                "LICENSE_SERVER_URL", "https://license.penguintech.io"
            )
            self.product_name = os.getenv("PRODUCT_NAME", "project-template")
            self.release_mode = os.getenv("RELEASE_MODE", "false").lower() == "true"

            self._features_cache: Dict[str, Any] = {}
            self._cache_expiry = 0
            self._full_cache_expiry = 0
            self._validation_cache: Dict[str, Any] = {}

            self._initialized = True

    def validate(self) -> bool:
        """
        Validate license on startup.

        Returns:
            bool: True if valid, False otherwise.
        """
        if not self.release_mode:
            logger.info("License validation skipped (RELEASE_MODE=false)")
            return True

        if not self.license_key:
            logger.error("LICENSE_KEY not set")
            return False

        try:
            response = requests.post(
                f"{self.server_url}/api/v2/validate",
                json={
                    "license_key": self.license_key,
                    "product_name": self.product_name,
                },
                timeout=5,
            )
            response.raise_for_status()
            data = response.json()

            if data.get("valid"):
                self._validation_cache = data
                self._full_cache_expiry = time.time() + (7 * 24 * 3600)
                logger.info(
                    f"License validated. Tier: {data.get('tier')}, "
                    f"Expires: {data.get('expires_at')}"
                )
                return True

            logger.error(f"License validation failed: {data.get('message')}")
            return False

        except Exception as e:
            logger.error(f"License validation error: {str(e)}")
            return False

    def is_feature_enabled(self, feature_name: str) -> bool:
        """
        Check if feature is enabled.

        Args:
            feature_name: Name of the feature to check.

        Returns:
            bool: True if feature is enabled.
        """
        if not self.release_mode:
            return True

        # Refresh cache if expired
        if time.time() > self._cache_expiry:
            self._refresh_features()

        features = self._features_cache.get("features", {})
        return features.get(feature_name, {}).get("enabled", False)

    def _refresh_features(self) -> None:
        """Refresh feature cache from server."""
        try:
            response = requests.post(
                f"{self.server_url}/api/v2/features",
                json={
                    "license_key": self.license_key,
                    "product_name": self.product_name,
                },
                timeout=5,
            )
            response.raise_for_status()
            self._features_cache = response.json()
            self._cache_expiry = time.time() + (5 * 60)  # 5 minutes

        except Exception as e:
            logger.warning(f"Failed to refresh features: {str(e)}")

    def get_tier(self) -> str:
        """Get license tier."""
        return self._validation_cache.get("tier", "community")

    def get_limits(self) -> Dict[str, Any]:
        """Get usage limits."""
        return self._validation_cache.get("limits", {})

    def checkin(self, usage_stats: Optional[Dict[str, Any]] = None) -> bool:
        """
        Send keepalive to license server.

        Args:
            usage_stats: Optional usage statistics to report.

        Returns:
            bool: True if successful.
        """
        if not self.release_mode or not self.license_key:
            return True

        try:
            payload = {
                "license_key": self.license_key,
                "product_name": self.product_name,
                "timestamp": datetime.utcnow().isoformat(),
            }

            if usage_stats:
                payload["usage_stats"] = usage_stats

            response = requests.post(
                f"{self.server_url}/api/v2/keepalive",
                json=payload,
                timeout=5,
            )
            response.raise_for_status()
            return True

        except Exception as e:
            logger.warning(f"Checkin failed: {str(e)}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get current license status."""
        return {
            "valid": bool(self._validation_cache),
            "tier": self.get_tier(),
            "features": self._features_cache.get("features", {}),
            "expires_at": self._validation_cache.get("expires_at"),
            "limits": self.get_limits(),
        }


def require_feature(feature_name: str):
    """
    Decorator to require a specific license feature.

    Args:
        feature_name: Name of the feature required.

    Raises:
        FeatureNotEntitledException: If feature is not enabled.
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            manager = LicenseManager()
            if not manager.is_feature_enabled(feature_name):
                return (
                    jsonify(
                        {
                            "error": "feature_not_entitled",
                            "message": f"Feature '{feature_name}' is not available in your license tier",
                        }
                    ),
                    403,
                )
            return f(*args, **kwargs)

        return decorated_function

    return decorator


# Initialize license manager
license_manager = LicenseManager()
