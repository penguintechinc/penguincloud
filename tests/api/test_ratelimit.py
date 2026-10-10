"""app.ratelimit — the counter/store logic underneath every `rate_limited` route.

Requirement (fresh deployment, nothing configured): every credential-
accepting route is throttled with CACHE_HOST unset, via the per-process
fallback alone. Requirement (Valkey configured but unreachable): the
fallback still enforces -- never "no limiting". See app/ratelimit.py's
module docstring for the full design rationale.
"""

from __future__ import annotations

import pytest
from app import ratelimit
from quart import Quart

MonkeyPatch = pytest.MonkeyPatch


def _set_ip_window(monkeypatch: MonkeyPatch, bucket: str, attempts: int, seconds: int) -> None:
    """Shorthand for overriding one bucket's IP-scoped window for a test."""
    monkeypatch.setitem(ratelimit._IP_WINDOWS, bucket, ratelimit._Window(attempts, seconds))


def _set_account_window(monkeypatch: MonkeyPatch, bucket: str, attempts: int, seconds: int) -> None:
    """Shorthand for overriding one bucket's account-scoped window for a test."""
    monkeypatch.setitem(ratelimit._ACCOUNT_WINDOWS, bucket, ratelimit._Window(attempts, seconds))


@pytest.mark.asyncio
async def test_first_attempts_are_admitted(app: Quart) -> None:
    """Under the limit, `check` returns None -- the view runs."""
    async with app.app_context(), app.test_request_context("/", method="POST"):
        assert await ratelimit.check("login") is None


@pytest.mark.asyncio
async def test_ip_window_refuses_once_exhausted(app: Quart, monkeypatch: MonkeyPatch) -> None:
    """The Nth+1 attempt inside the window is refused with 429."""
    _set_ip_window(monkeypatch, "login", attempts=3, seconds=60)

    async with app.app_context(), app.test_request_context("/", method="POST"):
        for _ in range(3):
            assert await ratelimit.check("login") is None

        refusal = await ratelimit.check("login")

    assert refusal is not None
    body, status = refusal
    assert status == 429
    assert body["error"] == "rate_limited"
    assert body["retry_after_seconds"] == 60


@pytest.mark.asyncio
async def test_account_window_is_independent_of_ip(app: Quart, monkeypatch: MonkeyPatch) -> None:
    """A different submitted email gets its own budget, same IP."""
    _set_account_window(monkeypatch, "login", attempts=2, seconds=60)
    # Wide open so only the account window can trip in this test.
    _set_ip_window(monkeypatch, "login", attempts=1000, seconds=60)

    async with app.app_context(), app.test_request_context("/", method="POST"):
        for _ in range(2):
            assert await ratelimit.check("login", account_key="victim@example.com") is None
        exhausted = await ratelimit.check("login", account_key="victim@example.com")
        assert exhausted is not None
        assert exhausted[1] == 429

        # A DIFFERENT account, same request context/IP, is unaffected.
        assert await ratelimit.check("login", account_key="someone-else@example.com") is None


def test_account_key_is_case_and_whitespace_normalised_by_the_caller() -> None:
    """Two casings of one address share a counter -- `_hash_subject` alone can't do this.

    email_account_key applies `.strip().lower()`; `check`/`_hash_subject`
    just hash whatever string they are given. This proves the two
    representations collide when passed through the same normalisation
    the login/register routes already apply.
    """
    normalised = "Victim@Example.com".strip().lower()
    assert ratelimit._hash_subject(normalised) == ratelimit._hash_subject("victim@example.com")


@pytest.mark.asyncio
async def test_a_bucket_with_no_table_entry_is_never_limited(app: Quart) -> None:
    """`check` on an undeclared bucket name is a no-op, not an error.

    Route wiring passes a bucket string; a typo must not silently 500 a
    production endpoint reachable by anonymous callers.
    """
    async with app.app_context(), app.test_request_context("/", method="POST"):
        for _ in range(50):
            assert await ratelimit.check("no_such_bucket") is None


@pytest.mark.asyncio
async def test_window_resets_after_it_elapses(app: Quart, monkeypatch: MonkeyPatch) -> None:
    """A fresh window admits attempts again -- this is a THROTTLE, not a ban."""
    _set_ip_window(monkeypatch, "login", attempts=1, seconds=10)
    fake_now = {"t": 1000.0}
    monkeypatch.setattr("app.ratelimit.time.monotonic", lambda: fake_now["t"])

    async with app.app_context(), app.test_request_context("/", method="POST"):
        assert await ratelimit.check("login") is None
        assert (await ratelimit.check("login"))[1] == 429  # type: ignore[index]

        fake_now["t"] += 11.0
        assert await ratelimit.check("login") is None


@pytest.mark.asyncio
async def test_unreachable_cache_host_still_enforces_via_local_fallback(
    app: Quart, monkeypatch: MonkeyPatch
) -> None:
    """The load-bearing property: a Valkey outage degrades scope, not to zero.

    Points CACHE_HOST at a real TCP port nothing listens on -- an
    OS-refused connection, not a multi-second timeout -- mirroring
    test_health_cache.py's own approach so this proves the actual failure
    path rather than a stand-in for it. Unlike health_cache, the outcome
    here must be ENFORCEMENT, not a graceful pass-through.
    """
    _set_ip_window(monkeypatch, "login", attempts=2, seconds=60)

    async with app.app_context():
        app.config["CACHE_HOST"] = "127.0.0.1"
        app.config["CACHE_PORT"] = 1

        async with app.test_request_context("/", method="POST"):
            assert await ratelimit.check("login") is None
            assert await ratelimit.check("login") is None
            refusal = await ratelimit.check("login")

    assert refusal is not None
    assert refusal[1] == 429


class _FakeSharedClient:
    """A minimal stand-in for AsyncValkeyCache, exercising the shared-store path.

    No real Valkey server is required in this venv (see
    test_health_cache.py's own `_FakeClient` for the same reasoning) --
    this proves `_bump`'s shared-store branch, including the
    increment-then-expire-on-first-hit sequencing, without one.
    """

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.expired: dict[str, int] = {}

        class _Raw:
            async def expire(_self, key: str, ttl: int) -> None:  # noqa: N805
                self.expired[key] = ttl

        self.client = _Raw()

    async def increment(self, key: str, amount: int = 1) -> int:
        self.counts[key] = self.counts.get(key, 0) + amount
        return self.counts[key]

    async def delete(self, key: str) -> None:
        self.counts.pop(key, None)


@pytest.mark.asyncio
async def test_shared_store_is_consulted_and_expiry_set_once(
    app: Quart, monkeypatch: MonkeyPatch
) -> None:
    """The Valkey-reachable path: increments the shared counter, sets TTL on the first hit only."""
    fake = _FakeSharedClient()
    monkeypatch.setattr(ratelimit, "_cache_client", fake)
    monkeypatch.setattr(ratelimit, "_cache_init_attempted", True)
    _set_ip_window(monkeypatch, "login", attempts=5, seconds=45)

    async with app.app_context(), app.test_request_context("/", method="POST"):
        await ratelimit.check("login")
        await ratelimit.check("login")

    assert any(v == 2 for v in fake.counts.values())
    assert any(v == 45 for v in fake.expired.values())
    assert len(fake.expired) == 1, "expire must be set on the FIRST hit only, not every hit"


@pytest.mark.asyncio
async def test_local_and_shared_counts_are_combined_with_max(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shared store that briefly under-reports must never look like fewer attempts happened.

    Simulates the shared store having missed earlier increments (e.g. a
    mid-window reconnect) by returning a count LOWER than the local
    counter's -- `_bump` must report the higher of the two, never let a
    shared-store hiccup reset a caller's effective count downward.
    """

    class _StaleRaw:
        async def expire(self, key: str, ttl: int) -> None:
            return None

    class _StaleClient:
        def __init__(self) -> None:
            self.client = _StaleRaw()

        async def increment(self, key: str, amount: int = 1) -> int:
            return 1  # always reports "first ever hit", regardless of reality

    monkeypatch.setattr(ratelimit, "_cache_client", _StaleClient())
    monkeypatch.setattr(ratelimit, "_cache_init_attempted", True)

    count = await ratelimit._bump("some-key", 60)
    count = await ratelimit._bump("some-key", 60)
    count = await ratelimit._bump("some-key", 60)

    # Local counter has genuinely seen 3 hits; the stale shared client keeps
    # reporting 1. The combined result must reflect the higher, true count.
    assert count == 3


class TestEmailAccountKey:
    """The helper login/forgot-password wire up as `account_key_fn`."""

    @pytest.mark.asyncio
    async def test_reads_and_normalises_the_email_field(self, app: Quart) -> None:
        """Case/whitespace variants collapse to one key -- see check()'s docstring."""
        async with app.test_request_context(
            "/", method="POST", json={"email": "  Someone@Example.COM  "}
        ):
            assert await ratelimit.email_account_key() == "someone@example.com"

    @pytest.mark.asyncio
    async def test_missing_field_is_none(self, app: Quart) -> None:
        """No email in the body -- `check` then falls back to IP-only."""
        async with app.test_request_context("/", method="POST", json={}):
            assert await ratelimit.email_account_key() is None

    @pytest.mark.asyncio
    async def test_non_json_body_is_none_not_an_error(self, app: Quart) -> None:
        """A malformed body must not 500 the rate limiter itself."""
        async with app.test_request_context("/", method="POST", data=b"not json"):
            assert await ratelimit.email_account_key() is None


class TestUserAccountKey:
    """The helper mfa.py/users.py wire up, reading the authenticated caller."""

    @pytest.mark.asyncio
    async def test_reads_g_current_user(self, app: Quart) -> None:
        """Requires `@auth_required` to have already set `g.current_user`."""
        from quart import g

        async with app.test_request_context("/", method="POST"):
            g.current_user = {"id": 42}
            assert await ratelimit.user_account_key() == "user:42"

    @pytest.mark.asyncio
    async def test_unauthenticated_is_none(self, app: Quart) -> None:
        """No authenticated caller -- `check` then falls back to IP-only."""
        async with app.test_request_context("/", method="POST"):
            assert await ratelimit.user_account_key() is None


@pytest.mark.asyncio
async def test_rate_limit_reset_clears_both_tiers(app: Quart, monkeypatch: MonkeyPatch) -> None:
    """The ops primitive named in the module docstring actually clears a lockout."""
    fake = _FakeSharedClient()
    monkeypatch.setattr(ratelimit, "_cache_client", fake)
    monkeypatch.setattr(ratelimit, "_cache_init_attempted", True)
    _set_ip_window(monkeypatch, "login", attempts=1, seconds=60)

    async with app.app_context(), app.test_request_context("/", method="POST"):
        await ratelimit.check("login")
        refused = await ratelimit.check("login")
        assert refused is not None

        await ratelimit.rate_limit_reset("login", ip=ratelimit._client_ip())

        assert await ratelimit.check("login") is None


def test_every_ip_bucket_has_a_sane_window() -> None:
    """Non-vacuity + sanity: every declared bucket is a real, positive window."""
    assert len(ratelimit._IP_WINDOWS) >= 8
    for name, window in ratelimit._IP_WINDOWS.items():
        assert window.max_attempts > 0, name
        assert window.seconds > 0, name


def test_every_account_bucket_is_narrower_than_its_ip_counterpart() -> None:
    """The account table exists to be the STRICTER one -- see module docstring.

    A bucket where the account window admits MORE than the IP window would
    make the account-scoped check pointless: the IP check would always
    trip first.
    """
    for bucket, account_window in ratelimit._ACCOUNT_WINDOWS.items():
        ip_window = ratelimit._IP_WINDOWS[bucket]
        assert account_window.max_attempts <= ip_window.max_attempts, bucket
