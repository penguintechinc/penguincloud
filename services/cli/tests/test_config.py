"""Tests for `pcli.config`."""

from __future__ import annotations

import pytest

from pcli.config import build_config, resolve_portal_url
from pcli.errors import ConfigurationError


def test_resolve_portal_url_explicit_wins() -> None:
    """Resolve portal url explicit wins."""
    assert resolve_portal_url("https://explicit.example.com/") == "https://explicit.example.com"


def test_resolve_portal_url_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve portal url falls back to env."""
    monkeypatch.setenv("PCLI_PORTAL_URL", "https://env.example.com")
    assert resolve_portal_url(None) == "https://env.example.com"


def test_resolve_portal_url_raises_when_neither_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve portal url raises when neither set."""
    monkeypatch.delenv("PCLI_PORTAL_URL", raising=False)
    with pytest.raises(ConfigurationError):
        resolve_portal_url(None)


def test_build_config_rejects_unknown_output_format() -> None:
    """Build config rejects unknown output format."""
    with pytest.raises(ConfigurationError):
        build_config(portal_url="https://x.example.com", output="xml")


def test_build_config_resolves_host_key() -> None:
    """Build config resolves host key."""
    config = build_config(portal_url="https://portal.example.com:8443/", output="json")
    assert config.host_key == "portal.example.com:8443"


def test_host_key_stable_across_http_and_https(monkeypatch: pytest.MonkeyPatch) -> None:
    """Host key stable across http and https."""
    http_config = build_config(portal_url="http://portal.example.com", output="json")
    https_config = build_config(portal_url="https://portal.example.com", output="json")
    assert http_config.host_key == https_config.host_key == "portal.example.com"
