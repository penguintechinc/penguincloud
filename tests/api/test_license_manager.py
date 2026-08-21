"""Unit coverage for app.license.LicenseManager's sync HTTP-adjacent methods.

get_tier/get_limits/checkin/validate were previously untested directly —
test_license.py only exercises the /license/status route, which never
reaches checkin() or validate()'s release-mode branches. LicenseManager is
a process-wide singleton (__new__ returns the same instance every call), so
these tests monkeypatch attributes on the INSTANCE, not env vars -- env
vars are only read once, at first construction.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from app import licensing
from app.license import LicenseManager


class _FakeLicenseInfo:
    """Fake License Info."""

    def __init__(
        self, valid: bool, message: str = "", limits: dict[str, Any] | None = None
    ) -> None:
        """Init."""
        self.valid = valid
        self.message = message
        self.limits = limits or {}
        from datetime import UTC, datetime

        self.expires_at = datetime.now(UTC)
        self.tier = "enterprise"


class _FakeLicenseClient:
    """Fake License Client."""

    def __init__(self, info: _FakeLicenseInfo) -> None:
        """Init."""
        self._info = info

    def validate(self, force_refresh: bool = False) -> _FakeLicenseInfo:
        """Validate."""
        return self._info


class TestGetTier:
    """Get Tier."""

    def test_delegates_to_licensing_module(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Delegates to licensing module."""
        monkeypatch.setattr(licensing, "resolve_tier_blocking", lambda: "enterprise")
        assert LicenseManager().get_tier() == "enterprise"


class TestGetLimits:
    """Get Limits."""

    def test_returns_the_clients_limits_as_a_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns the clients limits as a dict."""
        fake_client = _FakeLicenseClient(_FakeLicenseInfo(valid=True, limits={"max_users": 10}))
        monkeypatch.setattr(licensing, "get_client", lambda: fake_client)
        assert LicenseManager().get_limits() == {"max_users": 10}


class TestCheckin:
    """Checkin."""

    def test_non_release_mode_is_a_noop_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non release mode is a noop success."""
        manager = LicenseManager()
        monkeypatch.setattr(manager, "release_mode", False)
        assert manager.checkin() is True

    def test_release_mode_without_a_key_is_a_noop_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Release mode without a key is a noop success."""
        manager = LicenseManager()
        monkeypatch.setattr(manager, "release_mode", True)
        monkeypatch.setattr(manager, "license_key", "")
        assert manager.checkin() is True

    def test_release_mode_with_key_posts_and_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Release mode with key posts and succeeds."""
        manager = LicenseManager()
        monkeypatch.setattr(manager, "release_mode", True)
        monkeypatch.setattr(manager, "license_key", "real-key")
        monkeypatch.setattr(manager, "server_url", "https://license.example.com")

        captured: dict[str, Any] = {}

        class _FakeResponse:
            """Fake Response."""

            def raise_for_status(self) -> None:
                """Raise for status."""
                return None

        def _fake_post(url: str, json: dict[str, Any], timeout: int) -> _FakeResponse:
            """Fake post."""
            captured["url"] = url
            captured["json"] = json
            return _FakeResponse()

        monkeypatch.setattr(httpx, "post", _fake_post)

        assert manager.checkin(usage_stats={"users": 5}) is True
        assert captured["url"] == "https://license.example.com/api/v2/keepalive"
        assert captured["json"]["usage_stats"] == {"users": 5}

    def test_release_mode_with_key_swallows_http_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Release mode with key swallows http failure."""
        manager = LicenseManager()
        monkeypatch.setattr(manager, "release_mode", True)
        monkeypatch.setattr(manager, "license_key", "real-key")

        def _fake_post(*args: Any, **kwargs: Any) -> Any:
            """Fake post."""
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(httpx, "post", _fake_post)

        assert manager.checkin() is False

    def test_checkin_without_usage_stats_omits_the_field(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Checkin without usage stats omits the field."""
        manager = LicenseManager()
        monkeypatch.setattr(manager, "release_mode", True)
        monkeypatch.setattr(manager, "license_key", "real-key")

        captured: dict[str, Any] = {}

        class _FakeResponse:
            """Fake Response."""

            def raise_for_status(self) -> None:
                """Raise for status."""
                return None

        def _fake_post(url: str, json: dict[str, Any], timeout: int) -> _FakeResponse:
            """Fake post."""
            captured["json"] = json
            return _FakeResponse()

        monkeypatch.setattr(httpx, "post", _fake_post)

        manager.checkin()
        assert "usage_stats" not in captured["json"]


class TestValidate:
    """Validate."""

    def test_release_mode_without_key_is_invalid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Release mode without key is invalid."""
        manager = LicenseManager()
        monkeypatch.setattr(manager, "release_mode", True)
        monkeypatch.setattr(manager, "license_key", "")
        assert manager.validate() is False

    def test_valid_license_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Valid license returns true."""
        manager = LicenseManager()
        monkeypatch.setattr(manager, "release_mode", False)
        fake_client = _FakeLicenseClient(_FakeLicenseInfo(valid=True))
        monkeypatch.setattr(licensing, "get_client", lambda: fake_client)
        assert manager.validate() is True

    def test_invalid_license_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Invalid license returns false."""
        manager = LicenseManager()
        monkeypatch.setattr(manager, "release_mode", False)
        fake_client = _FakeLicenseClient(_FakeLicenseInfo(valid=False, message="license expired"))
        monkeypatch.setattr(licensing, "get_client", lambda: fake_client)
        assert manager.validate() is False
