"""Shared adapter transport: retries, timeouts, caps, credential injection.

The transport sits between every adapter and every product. Its retry policy
is the part most likely to be wrong in a way nothing notices: retrying too
much turns one rejected request into three against a rate-limited product
and can duplicate a non-idempotent write, while retrying too little makes a
single dropped connection look like a product outage.

``httpx.MockTransport`` is used throughout — httpx's own interception hook,
so the real client, the real header assembly and the real retry loop run;
only the socket is replaced.
"""

import asyncio
from typing import Any

import httpx
import pytest

from app.adapters.base import AdapterContext
from app.adapters.transport import (
    BACKOFF_BASE,
    MAX_ATTEMPTS,
    ResponseTooLargeError,
    Transport,
)


def _ctx(
    auth_type: str = "bearer", key: str = "secret-key", secret: str = ""
) -> AdapterContext:
    """Build a context for a transport call.

    ``base_url`` matches the host every test below calls: the transport pins
    each request to the connection's own origin (see
    ``Transport._assert_pinned_origin``), so a context pointing somewhere
    else would be refused before the socket — which is the point of the pin,
    and is asserted directly in TestOriginPinning.
    """
    return AdapterContext(
        connection_id=7,
        portal_tenant_id=3,
        external_id="ext-9",
        external_kind="tenant_id",
        base_url="https://p.invalid",
        auth_type=auth_type,
        api_key=key,
        api_secret=secret,
        correlation_id="corr-abc-123",
    )


def _transport(handler: Any, timeout: float = 10.0) -> Transport:
    """A Transport wired to an in-process handler instead of a socket."""
    instance = Transport(timeout=timeout)
    instance._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        timeout=httpx.Timeout(timeout),
    )
    return instance


@pytest.fixture(autouse=True)
def _no_real_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Collapse the backoff sleep so retry tests stay fast.

    The delay values themselves are asserted separately against the module
    constants; sleeping through them here would add seconds per test for no
    additional coverage.
    """

    async def _instant(_seconds: float) -> None:
        return None

    # asyncio.sleep is patched globally rather than as an attribute of
    # the transport module: mypy treats a re-exported stdlib import as
    # not-explicitly-exported, and patching the canonical object is
    # what the transport actually calls anyway.
    monkeypatch.setattr(asyncio, "sleep", _instant)


class _Recorder:
    """Handler that records each request and replies with a fixed response."""

    def __init__(self, status: int = 200, content: bytes = b"ok") -> None:
        self.requests: list[httpx.Request] = []
        self.status = status
        self.content = content

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, content=self.content)

    @property
    def last(self) -> httpx.Request:
        """The most recent request seen."""
        assert self.requests, "handler was never called"
        return self.requests[-1]


class _Counter:
    """Handler that fails a set number of times, then succeeds."""

    def __init__(self, fail_times: int, fail_status: int = 503) -> None:
        self.fail_times = fail_times
        self.fail_status = fail_status
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.calls <= self.fail_times:
            return httpx.Response(self.fail_status, content=b"transient")
        return httpx.Response(200, content=b'{"ok":true}')


@pytest.mark.asyncio
class TestRetryPolicy:
    """What is retried, what is not, and how many times."""

    async def test_transient_5xx_is_retried_then_succeeds(self) -> None:
        """A 503 that clears on the second attempt is invisible to the caller."""
        handler = _Counter(fail_times=1)
        transport = _transport(handler)

        response = await transport.request("GET", "https://p.invalid/x", _ctx())

        assert response.status_code == 200
        assert handler.calls == 2

    async def test_retries_are_bounded(self) -> None:
        """A product that is genuinely down is given up on, not hammered.

        The last attempt's response is returned rather than raising: a 503
        is the product's answer, and the caller decides what it means.
        """
        handler = _Counter(fail_times=99)
        transport = _transport(handler)

        response = await transport.request("GET", "https://p.invalid/x", _ctx())

        assert response.status_code == 503
        assert handler.calls == MAX_ATTEMPTS

    async def test_4xx_is_never_retried(self) -> None:
        """A 401 or 422 was answered correctly the first time.

        Retrying a client error multiplies a rejection that will not change,
        and against a rate limiter converts one refusal into three.
        """
        for status in (400, 401, 403, 404, 422, 429):
            handler = _Counter(fail_times=99, fail_status=status)
            transport = _transport(handler)

            response = await transport.request("GET", "https://p.invalid/x", _ctx())

            assert response.status_code == status
            assert handler.calls == 1, f"status {status} was retried"

    async def test_non_idempotent_methods_are_not_retried(self) -> None:
        """A retried POST can duplicate a side effect the product completed.

        A product that processed the request and then failed while
        responding looks identical to one that never received it, so POST
        and PATCH get exactly one attempt.
        """
        for method in ("POST", "PATCH"):
            handler = _Counter(fail_times=99)
            transport = _transport(handler)

            response = await transport.request(method, "https://p.invalid/x", _ctx())

            assert response.status_code == 503
            assert handler.calls == 1, f"{method} was retried"

    async def test_idempotent_methods_are_retried(self) -> None:
        """GET/PUT/DELETE are safe to repeat, so they are."""
        for method in ("GET", "PUT", "DELETE"):
            handler = _Counter(fail_times=1)
            transport = _transport(handler)

            response = await transport.request(method, "https://p.invalid/x", _ctx())

            assert response.status_code == 200
            assert handler.calls == 2, f"{method} was not retried"

    async def test_transport_errors_are_retried_then_raised(self) -> None:
        """A connect failure is retried; exhausting attempts re-raises.

        Raising rather than synthesising a status is deliberate: no response
        was produced, so nothing about the product's state is known and the
        caller must not be handed a fabricated one.
        """
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            raise httpx.ConnectError("no route to host", request=request)

        transport = _transport(handler)

        with pytest.raises(httpx.ConnectError):
            await transport.request("GET", "https://p.invalid/x", _ctx())

        assert calls["n"] == MAX_ATTEMPTS

    async def test_transport_error_recovers_within_budget(self) -> None:
        """One dropped connection does not surface as an outage."""
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.ConnectError("flap", request=request)
            return httpx.Response(200, content=b"ok")

        transport = _transport(handler)
        response = await transport.request("GET", "https://p.invalid/x", _ctx())

        assert response.status_code == 200
        assert calls["n"] == 2

    async def test_backoff_is_exponential(self, monkeypatch: Any) -> None:
        """Delays grow, so a struggling product is not retried at full rate."""
        slept: list[float] = []

        async def _record(seconds: float) -> None:
            slept.append(seconds)

        monkeypatch.setattr(asyncio, "sleep", _record)

        transport = _transport(_Counter(fail_times=99))
        await transport.request("GET", "https://p.invalid/x", _ctx())

        # One sleep per failed attempt that is followed by another.
        assert slept == [BACKOFF_BASE, BACKOFF_BASE * 2]


@pytest.mark.asyncio
class TestTimeouts:
    """Timeouts are bounded from above, whatever a caller asks for."""

    async def test_caller_timeout_is_clamped_to_the_maximum(self) -> None:
        """An adapter cannot pin a worker on a slow product indefinitely."""
        from app.adapters.transport import TIMEOUT_MAX

        seen: list[Any] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.extensions.get("timeout"))
            return httpx.Response(200, content=b"ok")

        transport = _transport(handler)
        await transport.request("GET", "https://p.invalid/x", _ctx(), timeout=600.0)

        assert seen[0] is not None
        assert max(v for v in seen[0].values() if v is not None) <= TIMEOUT_MAX

    async def test_constructor_timeout_is_clamped(self) -> None:
        """The clamp applies at construction too, not only per request."""
        from app.adapters.transport import TIMEOUT_MAX

        assert Transport(timeout=9999.0).timeout == TIMEOUT_MAX

    async def test_timeout_error_propagates_after_retries(self) -> None:
        """A read timeout is a RequestError: retried, then raised."""
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            raise httpx.ReadTimeout("too slow", request=request)

        transport = _transport(handler)

        with pytest.raises(httpx.ReadTimeout):
            await transport.request("GET", "https://p.invalid/x", _ctx())

        assert calls["n"] == MAX_ATTEMPTS


@pytest.mark.asyncio
class TestResponseSizeCap:
    """Every adapter call is capped, not just proxied passthroughs."""

    async def test_oversize_response_raises(self, monkeypatch: Any) -> None:
        """A hostile or broken product cannot exhaust memory."""
        import app.adapters.transport as transport_module

        monkeypatch.setattr(transport_module, "MAX_RESPONSE_SIZE", 64)
        transport = _transport(lambda request: httpx.Response(200, content=b"z" * 4096))

        with pytest.raises(ResponseTooLargeError):
            await transport.request("GET", "https://p.invalid/x", _ctx())

    async def test_response_at_the_cap_is_allowed(self, monkeypatch: Any) -> None:
        """The bound is inclusive — exactly at the cap is fine."""
        import app.adapters.transport as transport_module

        monkeypatch.setattr(transport_module, "MAX_RESPONSE_SIZE", 64)
        transport = _transport(lambda request: httpx.Response(200, content=b"z" * 64))

        response = await transport.request("GET", "https://p.invalid/x", _ctx())
        assert len(response.content) == 64


@pytest.mark.asyncio
class TestCredentialInjectionAndHeaders:
    """Auth headers are built from the context, per auth type."""

    async def test_bearer_auth_header(self) -> None:
        """bearer -> Authorization: Bearer <key>."""
        recorder = _Recorder()
        transport = _transport(recorder)

        await transport.request("GET", "https://p.invalid/x", _ctx())

        assert recorder.last.headers["authorization"] == "Bearer secret-key"

    async def test_api_key_auth_header(self) -> None:
        """api_key -> X-API-Key, with no Authorization at all."""
        recorder = _Recorder()
        transport = _transport(recorder)

        await transport.request("GET", "https://p.invalid/x", _ctx(auth_type="api_key"))

        assert recorder.last.headers["x-api-key"] == "secret-key"
        assert "authorization" not in recorder.last.headers

    async def test_basic_auth_header_is_encoded(self) -> None:
        """basic -> Authorization: Basic base64(key:secret)."""
        import base64

        recorder = _Recorder()
        transport = _transport(recorder)

        await transport.request(
            "GET",
            "https://p.invalid/x",
            _ctx(auth_type="basic", key="user", secret="pass"),
        )

        expected = base64.b64encode(b"user:pass").decode()
        assert recorder.last.headers["authorization"] == f"Basic {expected}"

    async def test_auth_type_none_injects_nothing(self) -> None:
        """An unauthenticated product gets no credential invented for it."""
        recorder = _Recorder()
        transport = _transport(recorder)

        await transport.request("GET", "https://p.invalid/x", _ctx(auth_type="none"))

        assert "authorization" not in recorder.last.headers
        assert "x-api-key" not in recorder.last.headers

    async def test_context_auth_overrides_caller_supplied_header(self) -> None:
        """A caller cannot smuggle its own Authorization past the context.

        The connection's credential wins unconditionally; otherwise an
        adapter bug (or a proxied header that escaped stripping) could
        authenticate as something other than the stored connection.
        """
        recorder = _Recorder()
        transport = _transport(recorder)

        await transport.request(
            "GET",
            "https://p.invalid/x",
            _ctx(),
            headers={"Authorization": "Bearer attacker-supplied"},
        )

        assert recorder.last.headers["authorization"] == "Bearer secret-key"

    async def test_correlation_id_is_propagated(self) -> None:
        """One id ties a portal request to the product call it caused."""
        recorder = _Recorder()
        transport = _transport(recorder)

        await transport.request("GET", "https://p.invalid/x", _ctx())

        assert recorder.last.headers["x-correlation-id"] == "corr-abc-123"

    async def test_retries_reuse_the_same_correlation_id(self) -> None:
        """Retries stay attributable to the originating request."""
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(503 if len(seen) == 1 else 200)

        transport = _transport(handler)
        await transport.request("GET", "https://p.invalid/x", _ctx())

        assert len(seen) == 2
        assert {r.headers["x-correlation-id"] for r in seen} == {"corr-abc-123"}


@pytest.mark.asyncio
class TestHealthCheck:
    """health_check maps transport outcomes onto HealthResult."""

    async def test_healthy_on_2xx(self) -> None:
        """A 2xx is healthy and carries a measured latency."""
        transport = _transport(lambda request: httpx.Response(200, content=b"ok"))

        result = await transport.health_check("https://p.invalid", "/healthz", _ctx())

        assert result.status == "healthy"
        assert result.status_code == 200
        assert result.error is None
        assert result.response_time_ms >= 0

    async def test_degraded_on_4xx(self) -> None:
        """The endpoint answered, but not affirmatively."""
        transport = _transport(lambda request: httpx.Response(404))

        result = await transport.health_check("https://p.invalid", "/healthz", _ctx())

        assert result.status == "degraded"
        assert result.status_code == 404

    async def test_unhealthy_on_5xx(self) -> None:
        """A persistent 5xx is unhealthy, after the retry budget."""
        transport = _transport(lambda request: httpx.Response(500))

        result = await transport.health_check("https://p.invalid", "/healthz", _ctx())

        assert result.status == "unhealthy"
        assert result.status_code == 500

    async def test_unreachable_is_unhealthy_not_an_exception(self) -> None:
        """A dead product degrades the dashboard; it does not 500 the portal.

        status_code 0 distinguishes "never answered" from any real HTTP
        status the product could have returned.
        """

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        transport = _transport(handler)
        result = await transport.health_check("https://p.invalid", "/healthz", _ctx())

        assert result.status == "unhealthy"
        assert result.status_code == 0
        assert result.error

    async def test_base_url_trailing_slash_does_not_double(self) -> None:
        """A trailing slash on base_url must not produce '//healthz'."""
        recorder = _Recorder()
        transport = _transport(recorder)

        await transport.health_check("https://p.invalid/", "/healthz", _ctx())

        assert recorder.last.url.path == "/healthz"


@pytest.mark.asyncio
async def test_transport_requires_connect_before_use() -> None:
    """An unconnected transport fails loudly rather than lazily opening.

    Silent lazy connection would create an un-pooled client per call,
    quietly discarding the connection reuse the shared transport exists for.
    """
    with pytest.raises(RuntimeError):
        await Transport().request("GET", "https://p.invalid/x", _ctx())


@pytest.mark.asyncio
async def test_close_is_idempotent() -> None:
    """Closing twice is safe — shutdown paths can overlap."""
    transport = _transport(lambda request: httpx.Response(200))
    await transport.close()
    await transport.close()
    assert transport._client is None
