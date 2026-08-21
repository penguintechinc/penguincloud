"""app.licensing's exception-swallowing branches (fail-closed on the paywall).

resolve_tier_blocking and is_feature_entitled_blocking both degrade to the
narrowest answer (TIER_COMMUNITY / not entitled) rather than raising when
the underlying LicenseClient misbehaves unexpectedly -- neither branch had
a test exercising the actual exception path.
"""

from __future__ import annotations

from typing import Any

import pytest
from app import licensing


class _ExplodingClient:
    """Exploding Client."""

    def validate(self) -> Any:
        """Validate."""
        raise RuntimeError("license server returned garbage")

    def check_feature(self, feature_name: str) -> bool:
        """Check feature."""
        raise AssertionError("not reached -- validate() explodes first")


class _FakeValidation:
    """Fake Validation."""

    def __init__(self, tier: str) -> None:
        """Init."""
        self.tier = tier


class _BelowTierGrantClient:
    """Tier alone denies, but check_feature grants a single-feature add-on."""

    def validate(self) -> _FakeValidation:
        """Validate."""
        return _FakeValidation(licensing.TIER_COMMUNITY)

    def check_feature(self, feature_name: str) -> bool:
        """Check feature."""
        return True


class TestResolveTierBlockingFailureMode:
    """Resolve Tier Blocking Failure Mode."""

    def test_client_exception_degrades_to_community(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Client exception degrades to community."""
        monkeypatch.setattr(licensing, "get_client", lambda: _ExplodingClient())
        assert licensing.resolve_tier_blocking() == licensing.TIER_COMMUNITY


class TestIsFeatureEntitledBlockingFailureMode:
    """Is Feature Entitled Blocking Failure Mode."""

    def test_client_exception_denies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Client exception denies."""
        monkeypatch.setattr(licensing, "get_client", lambda: _ExplodingClient())
        assert licensing.is_feature_entitled_blocking("sso_integration") is False

    def test_unknown_feature_name_denies_without_calling_the_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unknown feature name denies without calling the client."""
        called = {"get_client": False}

        def _track() -> Any:
            """Track."""
            called["get_client"] = True
            return _ExplodingClient()

        monkeypatch.setattr(licensing, "get_client", _track)
        assert licensing.is_feature_entitled_blocking("not-a-real-feature") is False
        assert called["get_client"] is False

    def test_below_tier_single_feature_grant_still_entitles(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A Community-tier client can still be entitled via check_feature."""
        monkeypatch.setattr(licensing, "get_client", lambda: _BelowTierGrantClient())
        assert licensing.is_feature_entitled_blocking("sso_integration") is True
