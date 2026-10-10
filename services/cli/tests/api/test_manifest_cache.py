"""Tests for `pcli.api.manifest_cache.ManifestCache` -- the tenant-keyed on-disk cache."""

from __future__ import annotations

import time
from pathlib import Path

from pcli.api.manifest_cache import STALE_AFTER_SECONDS, ManifestCache
from pcli.api.manifest_types import ConsoleManifest, ProductManifestEntry


def _entry(product_id: int, product_type: str) -> ProductManifestEntry:
    return ProductManifestEntry(
        product_id=product_id,
        product_type=product_type,
        manifest=ConsoleManifest(
            manifest_version=2,
            product_type=product_type,
            display_name=product_type.title(),
            resources=(),
        ),
    )


def test_load_returns_none_when_nothing_cached(tmp_path: Path) -> None:
    """Load returns none when nothing cached."""
    cache = ManifestCache("portal.example.com", root=tmp_path)
    assert cache.load(1) is None


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    """Save then load round trips."""
    cache = ManifestCache("portal.example.com", root=tmp_path)
    entries = (_entry(1, "gough"),)
    cache.save(1, entries)

    cached = cache.load(1)
    assert cached is not None
    assert cached.entries[0].product_type == "gough"
    assert cached.is_stale is False


def test_load_ignores_corrupt_cache_file(tmp_path: Path) -> None:
    """Load ignores corrupt cache file."""
    cache = ManifestCache("portal.example.com", root=tmp_path)
    path = tmp_path / "manifests" / "portal.example.com" / "1.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not valid json", encoding="utf-8")
    assert cache.load(1) is None


def test_stale_after_threshold(tmp_path: Path) -> None:
    """Stale after threshold."""
    cache = ManifestCache("portal.example.com", root=tmp_path)
    cache.save(1, (_entry(1, "gough"),))
    cached = cache.load(1)
    assert cached is not None
    # Force it stale by rewriting the timestamp directly on disk.
    path = tmp_path / "manifests" / "portal.example.com" / "1.json"
    import json

    data = json.loads(path.read_text())
    data["fetched_at"] = time.time() - STALE_AFTER_SECONDS - 60
    path.write_text(json.dumps(data), encoding="utf-8")

    stale_cached = cache.load(1)
    assert stale_cached is not None
    assert stale_cached.is_stale is True


def test_tenant_switch_does_not_leak_prior_cache(tmp_path: Path) -> None:
    """Falsification test: switching tenant_id never reads the OTHER tenant's cache.

    This repo shipped exactly this bug once already (a tenant switch served
    the previous tenant's rows under an identical cache key) -- this test
    pins that it cannot happen again for the on-disk manifest cache.
    """
    cache = ManifestCache("portal.example.com", root=tmp_path)
    cache.save(1, (_entry(100, "gough"),))
    cache.save(2, (_entry(200, "nest"),))

    tenant_1 = cache.load(1)
    tenant_2 = cache.load(2)
    assert tenant_1 is not None
    assert tenant_2 is not None
    assert tenant_1.entries[0].product_type == "gough"
    assert tenant_2.entries[0].product_type == "nest"
    assert tenant_1.entries != tenant_2.entries

    # A tenant with no cache entry of its own gets NOTHING -- never a
    # neighbour's cache under a coincidentally-matching key.
    assert cache.load(3) is None


def test_different_portal_hosts_do_not_share_cache_storage(tmp_path: Path) -> None:
    """Different portal hosts do not share cache storage."""
    cache_a = ManifestCache("a.example.com", root=tmp_path)
    cache_b = ManifestCache("b.example.com", root=tmp_path)
    cache_a.save(1, (_entry(1, "gough"),))
    assert cache_b.load(1) is None
