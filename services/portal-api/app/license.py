"""PenguinTech License Server Integration.

Uses httpx's synchronous client rather than ``requests``: the portal has one
HTTP library (see app/adapters/transport.py), and carrying a second one just
for three calls meant shipping — and patching — an extra dependency, plus a
second set of exception types for callers to know about.

These three calls are deliberately still SYNCHRONOUS. They run at startup
(validate) and from the background refresh path (features, keepalive), not
on a request path, so they do not block the event loop where it matters.
Making them async would change LicenseManager's public signatures and every
caller with them; that belongs in the licensing work, not here.

Entitlement decisions no longer live in this file. ``is_feature_enabled``
delegates to :mod:`app.licensing`, which resolves tier and per-feature
entitlement through ``penguin_licensing.LicenseClient`` and applies the ONE
permitted bypass (the hardcoded PenguinTech domain list). The env-var
bypass that used to sit at the top of ``is_feature_enabled`` is documented
in that method and in :mod:`app.licensing` so it cannot come back by
accident.
"""

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import datetime
from functools import wraps
from typing import Any, ParamSpec, TypeVar

import httpx
from quart import jsonify

from . import licensing

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


class FeatureNotEntitledError(Exception):
    """Exception raised when feature is not entitled."""

    pass


class LicenseManager:
    """Singleton license manager for PenguinTech License Server."""

    _instance: "LicenseManager | None" = None
    _lock = False

    def __new__(cls) -> "LicenseManager":
        """Return the single shared LicenseManager instance, creating it once."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize license manager."""
        if not hasattr(self, "_initialized"):
            self.license_key = os.getenv("LICENSE_KEY", "")
            self.server_url = os.getenv("LICENSE_SERVER_URL", "https://license.penguintech.io")
            self.product_name = os.getenv("PRODUCT_NAME", "project-template")
            self.release_mode = os.getenv("RELEASE_MODE", "false").lower() == "true"

            self._initialized = True

    def validate(self) -> bool:
        """Validate the license at startup.

        Delegates to the same ``penguin_licensing`` client every gate reads.
        The second httpx call and second cache this replaced were the reason
        a status endpoint could report one tier while the gates enforced
        another — one fact, one cache.

        ``release_mode`` survives here for one narrow purpose only: whether a
        FAILED validation is fatal at startup (see ``app/__init__.py``). It
        does not, and must not, decide whether any feature is entitled — that
        was the env-var bypass this work removed.

        Returns:
            bool: True if the license validated (or none is required).
        """
        if self.release_mode and not self.license_key:
            logger.error("LICENSE_KEY not set")
            return False

        info = licensing.get_client().validate(force_refresh=True)
        if info.valid:
            logger.info(
                "License validated. Tier: %s, Expires: %s",
                info.tier,
                info.expires_at.isoformat(),
            )
            return True

        logger.error("License validation failed: %s", info.message)
        return False

    def is_feature_enabled(self, feature_name: str) -> bool:
        """Check whether this deployment is ENTITLED to a licensed feature.

        Pure entitlement — no bypass of any kind is applied here. The only
        bypass there is (the hardcoded PenguinTech domain list) is applied
        by :meth:`is_feature_entitled` below, which has a request to read a
        host from.

        This used to open with::

            if not self.release_mode:
                return True

        which unlocked every Professional and Enterprise feature on any
        deployment that had not set ``RELEASE_MODE=true`` — the default.
        general.md forbids exactly that ("Bypass is domain-based ONLY —
        never via env vars, CLI args, or config flags"), and it was not a
        theoretical hole: SSO is gated through this method, so the entire
        Professional SSO surface was free for the price of an unset
        variable. Do not reintroduce an env-var short-circuit here in any
        form, including a "test mode" one.

        Args:
            feature_name: Name of the feature to check.

        Returns:
            bool: True if the license entitles this feature.
        """
        return licensing.is_feature_entitled_blocking(feature_name)

    async def is_feature_entitled(self, feature_name: str) -> bool:
        """Entitlement plus the domain bypass, off the event loop.

        Split from :meth:`is_feature_enabled` so the entitlement lookup —
        which can block on the license server — runs in a worker thread
        while the bypass, which cannot block, does not. The bypass reads
        CONFIGURATION (``licensing.configured_host``), not the request: it
        used to read ``request.host``, which meant any caller could claim
        the exemption with a header. Calls back through
        ``self.is_feature_enabled`` so a test that patches the sync
        predicate still governs the decision.
        """
        if licensing.current_host_is_license_exempt():
            return True
        return await asyncio.to_thread(self.is_feature_enabled, feature_name)

    def get_tier(self) -> str:
        """Get license tier, resolved through penguin-licensing.

        Reads the same client every gate reads rather than this class's own
        ``_validation_cache``: two caches of one fact is how a status
        endpoint comes to disagree with the gate it is meant to explain.
        """
        return licensing.resolve_tier_blocking()

    def get_limits(self) -> dict[str, Any]:
        """Get usage limits, from the same client the gates read."""
        return dict(licensing.get_client().validate().limits)

    def checkin(self, usage_stats: dict[str, Any] | None = None) -> bool:
        """Send keepalive to license server.

        Args:
            usage_stats: Optional usage statistics to report.

        Returns:
            bool: True if successful.
        """
        if not self.release_mode or not self.license_key:
            return True

        try:
            payload: dict[str, Any] = {
                "license_key": self.license_key,
                "product_name": self.product_name,
                "timestamp": datetime.utcnow().isoformat(),
            }

            if usage_stats:
                payload["usage_stats"] = usage_stats

            response = httpx.post(
                f"{self.server_url}/api/v2/keepalive",
                json=payload,
                timeout=5,
            )
            response.raise_for_status()
            return True

        except Exception as e:
            logger.warning(f"Checkin failed: {str(e)}")
            return False

    def get_status(self) -> dict[str, Any]:
        """Get current license status.

        Every field comes from the one ``penguin_licensing`` client, so this
        endpoint reports the state the gates actually enforce. Reading a
        second, locally-maintained cache is how a status page comes to say
        "professional" while every Professional route 403s.
        """
        info = licensing.get_client().validate()
        return {
            "valid": info.valid,
            "tier": info.tier,
            # A {name: {...}} lookup, not a list — tests/api/test_license.py
            # pins the shape, and is_feature_enabled's predecessor indexed
            # it that way.
            "features": {
                feature.name: {
                    "enabled": feature.entitled,
                    "units": feature.units,
                    "description": feature.description,
                }
                for feature in info.features
            },
            "expires_at": info.expires_at.isoformat(),
            "limits": dict(info.limits),
        }


def require_feature(
    feature_name: str,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[Any]]]:
    """Build a decorator gating an async view on a licensed feature.

    Quart views are coroutines, so the wrapper must be async and await the
    wrapped view — a sync wrapper would hand Quart an un-awaited coroutine.

    Goes through ``is_feature_entitled`` rather than the sync predicate so
    the domain bypass is evaluated with a request in hand and the license
    lookup does not block the event loop. The refusal body names both tiers
    (``licensing.upgrade_required``) so the UI can render an upgrade path
    instead of a dead end.
    """

    def decorator(f: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[Any]]:
        @wraps(f)
        async def decorated_function(*args: P.args, **kwargs: P.kwargs) -> Any:
            manager = LicenseManager()
            if not await manager.is_feature_entitled(feature_name):
                required = licensing.FEATURE_MIN_TIER.get(feature_name, licensing.TIER_ENTERPRISE)
                body = licensing.upgrade_required(
                    feature_name, required, await licensing.resolve_tier()
                )
                return jsonify(asdict(body)), 403
            return await f(*args, **kwargs)

        return decorated_function

    return decorator


# Initialize license manager
license_manager = LicenseManager()
