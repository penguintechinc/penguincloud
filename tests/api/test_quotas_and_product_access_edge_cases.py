"""Small remaining edge-case branches in app.quotas and app.product_access.

resolve_limits_blocking's exception fallback and minimum_tier_for's
"nothing admits this" branch had no direct test; product_access's
early-return tuples for an unauthenticated caller and a missing connection
were only reached incidentally (if at all) through the route tests.
"""

from __future__ import annotations

from typing import Any

import pytest
from app import licensing, product_access, quotas


class TestResolveLimitsBlockingFailureMode:
    """Resolve Limits Blocking Failure Mode."""

    def test_client_exception_degrades_to_community_limits(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Client exception degrades to community limits."""

        class _Exploding:
            def validate(self) -> Any:
                raise RuntimeError("license server unavailable")

        monkeypatch.setattr(licensing, "get_client", lambda: _Exploding())
        result = quotas.resolve_limits_blocking()
        assert result == quotas.DEFAULT_TIER_LIMITS[licensing.TIER_COMMUNITY]


class TestMinimumTierFor:
    """Minimum Tier For."""

    def test_no_tier_admits_an_unreasonably_large_value(self) -> None:
        """No tier admits an unreasonably large value."""
        assert quotas.minimum_tier_for("max_tenants", 10**9) is None

    def test_community_tier_is_returned_when_it_already_admits(self) -> None:
        """Community tier is returned when it already admits."""
        community_limit = quotas.DEFAULT_TIER_LIMITS[licensing.TIER_COMMUNITY].teams
        if community_limit == quotas.UNLIMITED or community_limit < 1:
            pytest.skip("teams on Community isn't a finite positive limit to probe")
        assert quotas.minimum_tier_for("teams", community_limit) == licensing.TIER_COMMUNITY


class TestResolveProductContextAuth:
    """Resolve Product Context Auth."""

    @pytest.mark.asyncio
    async def test_unauthenticated_caller_gets_401_tuple(
        self, app: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unauthenticated caller gets 401 tuple."""
        monkeypatch.setattr(product_access, "get_current_user", lambda: None)

        async with app.app_context():
            ctx, product_type, error = await product_access.resolve_product_context(
                1, product_access.ACTION_READ
            )

        assert ctx is None
        assert product_type is None
        assert error == ({"error": "User not authenticated"}, 401)

    @pytest.mark.asyncio
    async def test_unknown_connection_id_gets_not_found_tuple(
        self, app: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unknown connection id gets not found tuple."""
        monkeypatch.setattr(
            product_access, "get_current_user", lambda: {"id": 1, "email": "a@example.com"}
        )

        async with app.app_context():
            ctx, product_type, error = await product_access.resolve_product_context(
                9_999_999, product_access.ACTION_READ
            )

        assert ctx is None
        assert product_type is None
        assert error == product_access.NOT_FOUND
