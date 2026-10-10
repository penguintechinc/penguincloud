"""Async health poller for product connections (Phase 6).

Replaces the deleted ``services/go-backend``'s health-polling duty (see
``docs/APP_STANDARDS.md``): a background asyncio task, owned by
``app.background.BackgroundTaskManager``, that periodically probes every
ACTIVE product connection's ``health()`` and records the result for
``GET /api/v1/products/health`` (``app/health_api.py``) to read -- that
route never triggers a live check itself, only this sweep does.

Per-connection isolation
=========================
One connection's failure -- a timeout, an unknown product type, a bug in an
adapter -- must never affect any other connection's check in the same
sweep, and must never crash the sweep itself. Every per-connection failure
mode is caught inside :func:`_check_one` and turned into a synthetic
``unhealthy`` result with the failure recorded as its ``error``, so a
broken connection is *observable* (shows up as unhealthy, increments
``portal_product_health_poll_errors_total``) rather than silently dropped
from the cache.

Multi-replica caveat (documented, not solved here)
====================================================
``services/portal-api`` runs with ``hypercorn --workers 1`` (one process
per pod), so within a single pod there is exactly one poller instance --
no intra-pod duplication. Across REPLICAS, production defaults to 3+ pods
(devops-kubernetes.md), and each pod's poller sweeps the SAME set of
connections independently: N replicas means N times the load on every
connected product's health endpoint, and the ``product_connections.
health_status`` write-on-change below can interleave across pods (last
write wins; penguin-dal offers no cross-pod lock here). This mirrors the
same class of trade-off ``app.tenancy.resolver`` already documents for its
own in-process cache, and is called out explicitly rather than silently
shipped -- leader election / a distributed poll lock is a larger change
than Task 6 scopes and is left for a future phase if the duplicate load
proves to matter.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from penguintechinc_utils.logging import SanitizedLogger
from prometheus_client import Counter, Gauge, Histogram

from .adapters import get_adapter
from .adapters.base import AdapterContext
from .encryption import decrypt_value
from .health_cache import CachedHealth, set_health
from .models import get_active_product_connections, update_product_health

log = SanitizedLogger(__name__)

#: Requirement 1: "loop with 15s base interval + ±20% jitter".
BASE_INTERVAL_SECONDS: float = 15.0
JITTER_FRACTION: float = 0.2

#: Requirement 1: "per-call timeout (10s)" -- an OUTER guard around the
#: whole ``adapter.health(ctx)`` call, not the HTTP request timeout itself.
#: For every adapter built on ``HealthOnlyAdapter`` (all of them today),
#: ``transport.Transport.health_check`` applies its OWN ``timeout=5.0`` to
#: the actual GET (app/adapters/transport.py:363), so the real bound on a
#: healthy HTTP round-trip is 5s -- this 10s only fires for something
#: `health()` does beyond that single request (a bug, retry logic a future
#: adapter adds, a non-HTTP check), which is exactly why it exists as a
#: distinct, wider guard rather than being tuned to match transport's
#: number.
PER_CALL_TIMEOUT_SECONDS: float = 10.0

#: Requirement 1: "asyncio.Semaphore(50)".
MAX_CONCURRENT_CHECKS: int = 50

#: Crash-restart backoff for the SWEEP loop itself (requirement 4). Doubles
#: per consecutive failure, capped, then resets once a sweep succeeds.
CRASH_BACKOFF_BASE_SECONDS: float = 5.0
CRASH_BACKOFF_MAX_SECONDS: float = 300.0

#: Cap on a cached/logged error string. Guards against a large exception
#: message (a verbose upstream body httpx echoes back, a long redirect
#: chain) bloating the cache entry or the log line; the class of failure is
#: still fully identifiable from a truncated message.
MAX_ERROR_LENGTH: int = 500

#: Requirement 2: "gauge portal_product_health{connection,product}".
#: 1.0 when the last poll reported status == "healthy", else 0.0 --
#: "degraded"/"unhealthy"/"unknown" and a poll error are all not-1, which is
#: what an alerting rule wants to threshold on.
PRODUCT_HEALTH_GAUGE = Gauge(
    "portal_product_health",
    "1 when the connection's last health poll reported 'healthy', else 0",
    ["connection", "product"],
)

#: Requirement 2: "histogram poll latency".
POLL_LATENCY_HISTOGRAM = Histogram(
    "portal_product_health_poll_latency_seconds",
    "Wall-clock time of one product connection health poll",
    ["connection", "product"],
)

#: Requirement 2: "counter poll errors". Incremented only when the check
#: itself raised or timed out -- a plain "unhealthy" HealthResult is a
#: successful poll that answered "unhealthy", not a poll error.
POLL_ERRORS_COUNTER = Counter(
    "portal_product_health_poll_errors_total",
    "Polls that raised or timed out rather than returning a HealthResult",
    ["connection", "product"],
)

#: Guards start_metrics_server() so repeated `create_app()` calls in the
#: same process (every pytest test, notably) attempt the bind at most once.
_metrics_server_started = False


def start_metrics_server(port: int) -> None:
    """Serve Prometheus metrics on their own listener, once per process.

    A SEPARATE port rather than a route on the main Quart app on purpose:
    mounting ``/metrics`` on the JWT-authenticated app port means either it
    is unauthenticated (leaking connection ids and product types to
    whoever can reach the pod) or it is auth-gated (a default Prometheus
    scrape sends no bearer token, so it silently never scrapes). Matches
    the ``:9090`` convention ``backend-go.md``/``backend-rust.md`` already
    establish for this org's other services.

    ``prometheus_client.start_http_server`` spawns its own daemon thread
    and returns immediately -- it does not block the event loop. A bind
    failure (port already bound -- multiple hypercorn workers in one
    container, or a second ``create_app()`` call in the same process, as
    every test in this suite makes) is logged and swallowed rather than
    raised: metrics are an observability nicety, not something worth
    failing app startup over.
    """
    global _metrics_server_started
    if _metrics_server_started:
        return
    _metrics_server_started = True

    from prometheus_client import start_http_server

    try:
        start_http_server(port)
    except OSError as exc:
        log.warning("health_metrics_server_bind_failed", {"port": port, "error": str(exc)})


def next_interval(
    base: float = BASE_INTERVAL_SECONDS,
    jitter_fraction: float = JITTER_FRACTION,
    rand: Callable[[], float] = random.random,
) -> float:
    """One sweep interval: ``base`` scaled by ±``jitter_fraction``.

    ``rand`` is injectable (defaults to :func:`random.random`) so a test can
    assert the exact interval a deterministic sequence produces without
    patching the global ``random`` module -- see requirement 5, "jittered
    scheduling (mock clock)".
    """
    spread = base * jitter_fraction
    return base + (rand() * 2.0 - 1.0) * spread


def _truncate(text: str | None) -> str | None:
    """Cap an error string at :data:`MAX_ERROR_LENGTH`, or pass None through."""
    if text is None:
        return None
    if len(text) <= MAX_ERROR_LENGTH:
        return text
    return text[:MAX_ERROR_LENGTH] + "…(truncated)"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _build_context(conn: dict[str, Any]) -> AdapterContext:
    """Build the AdapterContext for one connection's health probe.

    ``external_id``/``external_kind`` are deliberately left empty:
    ``HealthOnlyAdapter.health()`` only ever reads ``ctx.base_url`` and the
    adapter's own ``HEALTH_ENDPOINT`` literal -- it never substitutes the
    ``{tenant}`` placeholder -- so resolving ``product_tenant_map`` here
    would be one extra DB query per connection per sweep for a value
    nothing in the health path reads.
    """
    return AdapterContext(
        connection_id=int(conn["id"]),
        portal_tenant_id=int(conn["tenant_id"]),
        external_id="",
        external_kind="",
        base_url=str(conn.get("base_url") or ""),
        auth_type=str(conn.get("auth_type") or "bearer"),
        api_key=decrypt_value(str(conn.get("api_key") or "")),
        api_secret=decrypt_value(str(conn.get("api_secret") or "")),
    )


async def _check_one(conn: dict[str, Any], semaphore: asyncio.Semaphore) -> None:
    """Poll one connection's health and record the outcome.

    Isolated by design: every exception the check itself can raise --
    ``get_adapter`` on an unregistered product type, a timeout, a bug deep
    in an adapter -- is caught here and turned into a synthetic unhealthy
    result. Nothing above this function ever sees an exception from a
    single connection's check, which is what makes "one connection's
    failure never affects others" (requirement 4) true rather than merely
    intended.
    """
    connection_id = int(conn["id"])
    product_type = str(conn.get("product_type") or "unknown")
    metric_labels = {"connection": str(connection_id), "product": product_type}

    async with semaphore:
        start = time.monotonic()
        try:
            ctx = _build_context(conn)
            adapter = get_adapter(product_type, ctx)
            result = await asyncio.wait_for(adapter.health(ctx), timeout=PER_CALL_TIMEOUT_SECONDS)
            elapsed = time.monotonic() - start
            entry = CachedHealth(
                status=result.status,
                latency_ms=result.response_time_ms,
                checked_at=_now_iso(),
                error=_truncate(result.error),
            )
            healthy = result.status == "healthy"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            elapsed = time.monotonic() - start
            entry = CachedHealth(
                status="unhealthy",
                latency_ms=int(elapsed * 1000),
                checked_at=_now_iso(),
                error=_truncate(str(exc)),
            )
            healthy = False
            POLL_ERRORS_COUNTER.labels(**metric_labels).inc()
            log.warning(
                "health_poll_error",
                {
                    "connection_id": connection_id,
                    "product": product_type,
                    "error": entry.error,
                },
            )

        POLL_LATENCY_HISTOGRAM.labels(**metric_labels).observe(elapsed)
        PRODUCT_HEALTH_GAUGE.labels(**metric_labels).set(1.0 if healthy else 0.0)

        try:
            await set_health(connection_id, entry)
        except Exception:
            # set_health() already catches its own cache-backend failures;
            # this is belt-and-suspenders against a bug in that bookkeeping
            # itself still not being allowed to take down the sweep.
            log.warning(
                "health_cache_write_unexpected_failure",
                {"connection_id": connection_id},
            )

        # Write-on-change only: an unconditional UPDATE per connection per
        # sweep (every 15s) would be a write amplification the existing
        # dashboard (app/dashboard_api.py) does not need -- it only reads
        # health_status when something ELSE renders the page.
        if conn.get("health_status") != entry.status:
            try:
                await update_product_health(connection_id, entry.status)
            except Exception:
                log.warning("health_poll_db_write_failed", {"connection_id": connection_id})


#: connection_id -> product_type, for every connection that reported a
#: metric series as of the last sweep. product_type is immutable once a
#: connection is created (products.update_product's editable field list
#: does not include it), so remembering it here is enough to build the
#: exact label tuple a stale series needs removed with -- see
#: _release_stale_series.
_tracked_connections: dict[int, str] = {}


def _release_stale_series(current: dict[int, str]) -> None:
    """Drop metric series for connections no longer in the active set.

    Fix wave 1 (I3): without this, a deleted or deactivated connection's
    gauge/histogram/counter series keep reporting their LAST value
    forever -- concretely, an alert on ``portal_product_health == 0``
    fires indefinitely for a connection an operator already removed -- and
    the series set grows monotonically with connection churn for the
    life of the process.
    """
    stale = _tracked_connections.keys() - current.keys()
    for connection_id in stale:
        product_type = _tracked_connections[connection_id]
        labelvalues = (str(connection_id), product_type)
        for metric in (PRODUCT_HEALTH_GAUGE, POLL_LATENCY_HISTOGRAM, POLL_ERRORS_COUNTER):
            try:
                metric.remove(*labelvalues)
            except KeyError:
                # Nothing to remove -- e.g. a connection that was created
                # and deactivated between sweeps without ever being
                # checked, so it never had a series to begin with.
                pass
    _tracked_connections.clear()
    _tracked_connections.update(current)


def reset_tracked_connections_for_tests() -> None:
    """Forget which connections currently hold a metric series. Test hook only.

    ``_tracked_connections`` is module-level (same reasoning as
    ``app.health_cache``'s in-process fallback), so without this a
    connection_id a previous test tracked can shadow what a later test
    expects to see as newly-active or newly-stale.
    """
    _tracked_connections.clear()


async def run_sweep() -> None:
    """One full pass over every active product connection.

    Fetches the connection list once, releases metric series for any
    connection that dropped out since the last sweep, then checks every
    remaining connection concurrently under a shared semaphore
    (requirement 1: ``asyncio.Semaphore(50)``).
    """
    connections = await get_active_product_connections()
    current = {int(conn["id"]): str(conn.get("product_type") or "unknown") for conn in connections}
    _release_stale_series(current)

    if not connections:
        return
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)
    await asyncio.gather(*(_check_one(conn, semaphore) for conn in connections))


async def poll_forever(should_continue: Callable[[], bool]) -> None:
    """Sweep on a jittered interval until ``should_continue()`` is false.

    ``should_continue`` is a callback rather than an internal flag so
    :class:`app.background.BackgroundTaskManager` stays the single owner of
    run/stop state (``lambda: self._running``) -- this module has no
    lifecycle of its own to get out of sync with it.

    Crash-restarts with exponential backoff (requirement 4) when the sweep
    bookkeeping ITSELF raises -- something outside :func:`_check_one`'s own
    per-connection isolation, e.g. a bug in :func:`run_sweep` or a
    ``get_active_product_connections`` failure. This is exactly the
    resilience the license keepalive loop in ``app/background.py`` has
    never had (Task 6 brief): that loop logs and continues at its fixed
    interval, this one backs off.
    """
    consecutive_failures = 0
    while should_continue():
        try:
            await run_sweep()
            consecutive_failures = 0
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            consecutive_failures += 1
            backoff = min(
                CRASH_BACKOFF_BASE_SECONDS * (2 ** (consecutive_failures - 1)),
                CRASH_BACKOFF_MAX_SECONDS,
            )
            log.error(
                "health_poll_loop_crashed",
                {
                    "attempt": consecutive_failures,
                    "error": _truncate(str(exc)),
                    "backoff_seconds": backoff,
                },
            )
            await asyncio.sleep(backoff)
            continue

        if not should_continue():
            break
        await asyncio.sleep(next_interval())
