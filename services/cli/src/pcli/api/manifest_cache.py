"""Tenant-keyed on-disk manifest cache -- a security property, not just speed.

Cached at `~/.config/pcli/manifests/{portal_host}/{tenant_id}.json`, keyed
by BOTH the portal host and the tenant id. This repo shipped a cross-tenant
cache-key leak once already (a tenant switch served the previous tenant's
rows under an identical cache key) -- on disk, across process invocations,
that class of bug is worse: a stale, wrong-tenant manifest would persist
indefinitely instead of expiring with a request-scoped cache. Keying on
`tenant_id` (never on nothing, never shared across tenants) is what makes
switching tenants (`pcli tenants use`) provably unable to read a prior
tenant's cached command tree -- see
`tests/api/test_manifest_cache.py::test_tenant_switch_does_not_leak_prior_cache`.

A cache read that fails (missing, unreadable, corrupt JSON) is not fatal --
`load()` returns None and the caller falls back to a live fetch. A cache
HIT past its staleness threshold is still returned (client.md: never crash
on a network error, use cached data with an age warning) -- `CachedManifests.
is_stale` is informational, surfaced by the caller as a warning, not
enforced here.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .manifest_types import ProductManifestEntry

#: Cache entries older than this are still served, but flagged stale --
#: client.md: "Stale data awareness: show cached data age to user."
STALE_AFTER_SECONDS: float = 15 * 60.0


def _config_root() -> Path:
    """`~/.config/pcli` (or `$XDG_CONFIG_HOME/pcli` when set)."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "pcli"


def _cache_path(portal_host: str, tenant_id: int, *, root: Path | None = None) -> Path:
    base = root if root is not None else _config_root()
    # Host segment sanitised: a portal host is attacker-influenced only in
    # the sense that a caller chooses which host to point pcli at, never
    # server-controlled input reaching this process -- but sanitising
    # anyway costs nothing and keeps an unusual host (custom port, IPv6
    # literal) from producing a path separator.
    safe_host = portal_host.replace("/", "_").replace(":", "_")
    return base / "manifests" / safe_host / f"{tenant_id}.json"


@dataclass(slots=True, frozen=True)
class CachedManifests:
    """A cached manifest set, plus how old it is."""

    entries: tuple[ProductManifestEntry, ...]
    fetched_at: float

    @property
    def age_seconds(self) -> float:
        """Seconds since this cache entry was written."""
        return max(0.0, time.time() - self.fetched_at)

    @property
    def is_stale(self) -> bool:
        """True once `age_seconds` exceeds `STALE_AFTER_SECONDS`."""
        return self.age_seconds > STALE_AFTER_SECONDS


class ManifestCache:
    """Reads/writes the tenant-keyed on-disk manifest cache for one portal host."""

    def __init__(self, portal_host: str, *, root: Path | None = None) -> None:
        """`portal_host` should be `CLIConfig.host_key`; `root` is test-only override."""
        self._portal_host = portal_host
        self._root = root

    def load(self, tenant_id: int) -> CachedManifests | None:
        """Read the cached manifest set for `tenant_id`, or None if absent/unreadable."""
        path = _cache_path(self._portal_host, tenant_id, root=self._root)
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            data: dict[str, Any] = json.loads(raw)
            entries = tuple(ProductManifestEntry.from_wire(e) for e in data["entries"])
            fetched_at = float(data["fetched_at"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            # Corrupt cache: treat identically to "no cache" rather than
            # raising -- a live fetch recovers cleanly either way.
            return None
        return CachedManifests(entries=entries, fetched_at=fetched_at)

    def save(self, tenant_id: int, entries: tuple[ProductManifestEntry, ...]) -> None:
        """Write `entries` to the cache for `tenant_id`, timestamped now."""
        path = _cache_path(self._portal_host, tenant_id, root=self._root)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fetched_at": time.time(),
            "entries": [_entry_to_wire(e) for e in entries],
        }
        path.write_text(json.dumps(payload), encoding="utf-8")


def _entry_to_wire(entry: ProductManifestEntry) -> dict[str, Any]:
    """Serialise a `ProductManifestEntry` back to the wire shape `from_wire` parses.

    Round-trips through the same field names the portal serves, rather than
    a bespoke cache format, so `ManifestCache.load`/`save` and a live
    `PortalClient.list_manifests()` response are interchangeable to every
    caller.
    """
    manifest = entry.manifest
    return {
        "product_id": entry.product_id,
        "product_type": entry.product_type,
        "manifest": {
            "manifest_version": manifest.manifest_version,
            "product_type": manifest.product_type,
            "display_name": manifest.display_name,
            "nav": {
                "items": [
                    {"kind": i.kind, "label": i.label, "icon": i.icon} for i in manifest.nav_items
                ]
            },
            "resources": [_resource_to_wire(r) for r in manifest.resources],
        },
    }


def _resource_to_wire(resource: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "kind": resource.kind,
        "label": resource.label,
        "plural_label": resource.plural_label,
        "id_field": resource.id_field,
        "name_field": resource.name_field,
        "transport": resource.transport,
        "empty_state": resource.empty_state,
        "error_state": resource.error_state,
        "columns": [_column_to_wire(c) for c in resource.columns],
    }
    if resource.list is not None:
        body["list"] = {
            "path_bytes": resource.list.path_bytes,
            "envelope": {"keys": list(resource.list.envelope.keys)},
            "pagination": resource.list.pagination,
        }
    if resource.item_path is not None:
        body["item_path"] = {
            "prefix": resource.item_path.prefix,
            "sample_id": resource.item_path.sample_id,
        }
    return body


def _column_to_wire(column: Any) -> dict[str, Any]:
    cell = column.cell
    return {
        "field": column.field,
        "label": column.label,
        "sortable": column.sortable,
        "absent_as": column.absent_as,
        "cell": {
            "kind": cell.kind,
            "unit": cell.unit,
            "relative": cell.relative,
            "currency_field": cell.currency_field,
            "to_kind": cell.to_kind,
            "id_field": cell.id_field,
            "labels": (
                {"true_label": cell.labels.true_label, "false_label": cell.labels.false_label}
                if cell.labels
                else None
            ),
            "styles": [{"value": s.value, "style": s.style} for s in cell.styles],
        },
    }
