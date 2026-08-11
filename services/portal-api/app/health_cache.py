"""Shared store for the health poller's per-connection results.

Two tiers, deliberately layered
================================
1. **Valkey (penguin-dal's AsyncValkeyCache)** -- the cross-worker,
   cross-replica source of truth. Every hypercorn worker/pod that reads
   ``health:{connection_id}`` sees what the poller last wrote, wherever it
   ran.
2. **Per-process in-memory fallback** -- written unconditionally alongside
   the Valkey write, read only when Valkey is unset or unreachable. This is
   what Task 6's "poller survives Redis outages (degrades to in-memory
   last-known)" requirement actually means in a multi-replica deployment: a
   worker that cannot reach Valkey still answers ``GET
   /api/v1/products/health`` with the last status *this worker's own
   poller* observed, not a 500 and not silence. Cross-worker freshness is
   lost for the outage's duration -- the same trade-off
   ``app.tenancy.resolver`` documents for its own in-process cache -- but a
   single connection's data never disappears just because the shared store
   is down.

Cache key is ``health:{connection_id}`` -- no tenant id. The endpoint
(``app/health_api.py``) only ever looks up connections it already resolved
through a tenant-scoped, authorised DB query, so a stale or even poisoned
cache entry cannot widen what a caller may see: it can make one connection's
status stale, never surface a connection the caller was not already
authorised to read.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

from quart import current_app

logger = logging.getLogger(__name__)

#: ``health:{connection_id}`` -- see module docstring for why no tenant id.
CACHE_KEY_PREFIX = "health:"

#: Local fallback entries expire on the same clock as the shared cache, so a
#: worker never reports a connection "healthy" from a check that happened
#: outside the freshness window the endpoint's callers expect.
_DEFAULT_TTL_SECONDS = 60


@dataclass(slots=True, frozen=True)
class CachedHealth:
    """One connection's last observed health, as stored and served."""

    status: str
    latency_ms: int
    checked_at: str  # ISO 8601, UTC
    error: str | None = None


#: connection_id -> (expires_at_monotonic, entry). Per-process; see module
#: docstring. Never imported/exported across workers -- that is the point.
_LOCAL_FALLBACK: dict[int, tuple[float, CachedHealth]] = {}

#: Lazily constructed, then reused for the life of the process. `None` after
#: a failed/absent-config init attempt so we do not retry building a client
#: from config that will not change without a restart -- an actual network
#: outage is retried every call, since constructing AsyncValkeyCache does not
#: itself connect (the underlying valkey.asyncio.Valkey client connects
#: lazily on first command).
_cache_client: Any = None
_cache_init_attempted = False


def _cache_key(connection_id: int) -> str:
    return f"{CACHE_KEY_PREFIX}{connection_id}"


def log_startup_state(app_config: Any) -> None:
    """Log, unmistakably, whether the shared health cache is CONFIGURED.

    Fix wave 2 (W2-3): deliberately checks config presence, not actual
    reachability -- a startup hook must not block app boot on a network
    round-trip to Valkey. "Configured" and "reachable" are different
    claims: CACHE_HOST set but pointing at something unreachable (wrong
    host, valkey library missing, network policy denying it) still logs
    ``health_cache_shared_store_configured`` here, and then
    ``health_cache_disabled`` from the lazy first read in
    _get_cache_client -- which is correct, not a contradiction, once this
    function only claims "configured". Read the two log lines together
    for the full picture: this one at startup, the other (if it ever
    fires) on the first actual cache access.

    Fix wave 1 (I4): CACHE_HOST has no consumer outside this module in any
    deployment definition currently in this repo (docker-compose.yml sets
    REDIS_URL, which this does NOT read; the Helm charts under
    k8s/helm/{portal-api,webui,project-template}/ are stubs), so a
    deployment that never set CACHE_HOST would silently run the
    per-process-only fallback with no operator-visible signal beyond a
    DEBUG-level line on the first cache read. Called once at app startup
    (app/__init__.py's _start_background_tasks) rather than left to that
    lazy first read, so the consequence is visible in the FIRST few lines
    of a fresh deployment's logs, not buried after the first poll cycle.

    Mirrors the operator-notice reasoning general.md requires for --dev
    mode: someone who did not configure the deployment needs to know what
    mode it is running in, in terms of the actual consequence, not a bare
    state label.
    """
    host = str(app_config.get("CACHE_HOST", "") or "")
    if host:
        logger.info("health_cache_shared_store_configured host=%s", host)
        return

    logger.warning(
        "health_cache_is_per_process_only reason=CACHE_HOST_not_configured "
        "consequence='GET /api/v1/products/health results are NOT shared "
        "across workers or replicas -- each process answers only from what "
        "its own poller has observed, and two requests landing on "
        "different pods can disagree about the same connection' "
        "fix='set CACHE_HOST (docs/DEVELOPMENT.md: Health Cache (Valkey/Redis)); "
        "REDIS_URL is a different variable and is NOT read here'"
    )


def _ttl_seconds() -> int:
    try:
        return int(current_app.config.get("HEALTH_POLL_CACHE_TTL_SECONDS", _DEFAULT_TTL_SECONDS))
    except RuntimeError:
        # No app context (e.g. a unit test calling the pure cache layer
        # directly) -- the module-level default is the only sane answer.
        return _DEFAULT_TTL_SECONDS


async def _get_cache_client() -> Any | None:
    """Return the shared Valkey client, building it once, or None.

    None means "no shared cache available for this process" -- either
    nothing is configured (CACHE_HOST unset, the common case in tests and
    single-worker dev) or the client library/import failed. Both are
    logged once and then treated identically by every caller: fall back to
    the in-process store.
    """
    global _cache_client, _cache_init_attempted

    if _cache_client is not None:
        return _cache_client
    if _cache_init_attempted:
        return None
    _cache_init_attempted = True

    host = str(current_app.config.get("CACHE_HOST", "") or "")
    if not host:
        logger.warning("health_cache_disabled reason=CACHE_HOST_not_configured")
        return None

    try:
        from penguin_dal.cache.valkey import AsyncValkeyCache, ValkeyConfig
    except ImportError:
        logger.warning("health_cache_disabled reason=penguin_dal.cache.valkey_unavailable")
        return None

    try:
        _cache_client = AsyncValkeyCache(
            ValkeyConfig(
                host=host,
                port=int(current_app.config.get("CACHE_PORT", 6379)),
                db=int(current_app.config.get("CACHE_DB", 0)),
                password=str(current_app.config.get("CACHE_PASS", "") or "") or None,
                ssl=bool(current_app.config.get("CACHE_SSL", False)),
                prefix="",
            )
        )
    except ImportError:
        # AsyncValkeyCache.__init__ imports `valkey.asyncio` itself and
        # raises ImportError if the client library is missing even though
        # penguin_dal.cache.valkey imported fine.
        logger.warning("health_cache_disabled reason=valkey_client_library_missing")
        return None

    return _cache_client


def _remember_locally(connection_id: int, entry: CachedHealth, ttl_seconds: int) -> None:
    _LOCAL_FALLBACK[connection_id] = (time.monotonic() + ttl_seconds, entry)


def _recall_locally(connection_id: int) -> CachedHealth | None:
    cached = _LOCAL_FALLBACK.get(connection_id)
    if cached is None:
        return None
    expires_at, entry = cached
    if expires_at <= time.monotonic():
        _LOCAL_FALLBACK.pop(connection_id, None)
        return None
    return entry


async def set_health(connection_id: int, entry: CachedHealth) -> None:
    """Record one connection's health. Never raises.

    Always writes the in-process fallback first (cheap, cannot fail), then
    attempts the shared store. A Valkey write failure is logged and
    swallowed -- one connection's poll must never fail the sweep, and a
    cache outage must never crash the poller (Task 6 requirement 4).
    """
    ttl_seconds = _ttl_seconds()
    _remember_locally(connection_id, entry, ttl_seconds)

    try:
        client = await _get_cache_client()
    except Exception:
        logger.warning("health_cache_client_init_failed", extra={"connection_id": connection_id})
        return
    if client is None:
        return

    try:
        payload = json.dumps(asdict(entry)).encode("utf-8")
        await client.set(_cache_key(connection_id), payload, ttl=ttl_seconds)
    except Exception:
        logger.warning("health_cache_write_failed", extra={"connection_id": connection_id})


async def get_health(connection_id: int) -> CachedHealth | None:
    """Return the last recorded health for a connection, or None.

    Tries the shared store first so every worker/pod sees the same answer
    when it is reachable; falls back to this process's own last-known value
    otherwise. Never triggers a live check -- see app/health_api.py.
    """
    try:
        client = await _get_cache_client()
    except Exception:
        client = None

    if client is not None:
        try:
            raw = await client.get(_cache_key(connection_id))
        except Exception:
            logger.warning("health_cache_read_failed", extra={"connection_id": connection_id})
            raw = None
        if raw is not None:
            try:
                data = json.loads(raw)
                return CachedHealth(**data)
            except (ValueError, TypeError, KeyError):
                logger.warning("health_cache_corrupt_entry", extra={"connection_id": connection_id})

    return _recall_locally(connection_id)


def clear_local_cache() -> None:
    """Empty the in-process fallback outright. Test and shutdown hook."""
    _LOCAL_FALLBACK.clear()


async def close_cache_client() -> None:
    """Release the shared Valkey connection, if one was ever opened."""
    global _cache_client, _cache_init_attempted
    if _cache_client is not None:
        try:
            await _cache_client.close()
        except Exception:
            logger.warning("health_cache_close_failed")
    _cache_client = None
    _cache_init_attempted = False


def reset_cache_client_for_tests() -> None:
    """Forget the memoised client/init state. Test isolation hook only.

    Does NOT close the client -- tests never open a real one (CACHE_HOST is
    unset under TestingConfig), so there is nothing to close; this only
    exists so one test setting CACHE_HOST via monkeypatch cannot leak a
    cached (None or real) client into the next.
    """
    global _cache_client, _cache_init_attempted
    _cache_client = None
    _cache_init_attempted = False
