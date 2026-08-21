"""Unit tests for the Killkrill receiver client package.

app.killkrill_client.{client,rest_client,grpc_client} are pure-Python
network clients with no Quart app dependency — httpx/grpc are faked at the
module boundary rather than requiring a live receiver. Previously entirely
untested (0 files in tests/api referenced killkrill_client), which is the
biggest single coverage gap in the backend: client.py, rest_client.py and
grpc_client.py were 27%/20%/22% covered respectively.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock

import grpc
import httpx
import pytest
from app.killkrill_client.client import ReceiverClient, TokenInfo
from app.killkrill_client.exceptions import (
    AuthenticationError,
    SubmissionError,
)
from app.killkrill_client.exceptions import (
    ConnectionError as ReceiverConnectionError,
)
from app.killkrill_client.grpc_client import GRPCSubmitter
from app.killkrill_client.rest_client import RESTSubmitter


class _FakeResponse:
    """Stand-in for httpx.Response, exposing only what these clients read."""

    def __init__(
        self, status_code: int, json_data: dict[str, Any] | None = None, text: str = ""
    ) -> None:
        """Init."""
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self) -> dict[str, Any]:
        """Json."""
        return self._json


class _FakeAsyncClient:
    """httpx.AsyncClient stand-in driven by canned get()/post() responses.

    Supports both call shapes these clients use: RESTSubmitter holds an
    instance directly (`self.client = httpx.AsyncClient(...)`), while
    ReceiverClient uses it as an `async with` context manager.
    """

    def __init__(
        self,
        *args: Any,
        get_response: _FakeResponse | Exception | None = None,
        post_response: _FakeResponse | Exception | None = None,
        **kwargs: Any,
    ) -> None:
        """Init."""
        self.get_response = get_response
        self.post_response = post_response
        self.closed = False

    async def get(self, path: str, **kwargs: Any) -> _FakeResponse:
        """Get."""
        if isinstance(self.get_response, Exception):
            raise self.get_response
        assert self.get_response is not None
        return self.get_response

    async def post(self, path: str, **kwargs: Any) -> _FakeResponse:
        """Post."""
        if isinstance(self.post_response, Exception):
            raise self.post_response
        assert self.post_response is not None
        return self.post_response

    async def aclose(self) -> None:
        """Aclose."""
        self.closed = True

    async def __aenter__(self) -> _FakeAsyncClient:
        """Aenter."""
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        """Aexit."""
        return False


class _FakeRpcError(grpc.RpcError):  # type: ignore[misc]  # grpc.RpcError is untyped (Any)
    """grpc.RpcError stand-in carrying the code()/details() the app reads."""

    def __init__(self, code: str = "UNAVAILABLE", details: str = "receiver unreachable") -> None:
        """Init."""
        super().__init__()
        self._code = code
        self._details = details

    def code(self) -> str:
        """Code."""
        return self._code

    def details(self) -> str:
        """Details."""
        return self._details


class _FakeChannel:
    """Fake Channel."""

    def __init__(self) -> None:
        """Init."""
        self.closed = False

    def close(self) -> None:
        """Close."""
        self.closed = True


class _FakeReadyFuture:
    """Fake Ready Future."""

    def __init__(self, outcome: str) -> None:
        """Init."""
        self._outcome = outcome

    def result(self, timeout: float | None = None) -> None:
        """Result."""
        if self._outcome == "ready":
            return
        if self._outcome == "timeout":
            raise grpc.FutureTimeoutError()
        raise RuntimeError("channel never became ready")


class TestTokenInfo:
    """TokenInfo.is_expired() — the branch that decides re-auth vs refresh."""

    def test_not_expired_well_before_deadline(self) -> None:
        """Not expired well before deadline."""
        from datetime import UTC, datetime, timedelta

        token = TokenInfo(
            access_token="a",
            refresh_token="r",
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
        )
        assert token.is_expired() is False

    def test_expired_within_the_5_minute_safety_margin(self) -> None:
        """Expired within the 5 minute safety margin."""
        from datetime import UTC, datetime, timedelta

        # Within the 5-minute margin subtracted in is_expired() -- must
        # read as expired even though the raw expiry is still in the future.
        token = TokenInfo(
            access_token="a",
            refresh_token="r",
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=2),
        )
        assert token.is_expired() is True


class TestRESTSubmitterConnect:
    """R E S T Submitter Connect."""

    @pytest.mark.asyncio
    async def test_connect_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Connect success."""
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda *a, **k: _FakeAsyncClient(*a, get_response=_FakeResponse(200), **k),
        )
        submitter = RESTSubmitter("https://receiver.example.com", "tok")
        assert await submitter.connect() is True
        assert submitter.client is not None

    @pytest.mark.asyncio
    async def test_connect_unhealthy_still_returns_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Connect unhealthy still returns false."""
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda *a, **k: _FakeAsyncClient(*a, get_response=_FakeResponse(503), **k),
        )
        submitter = RESTSubmitter("https://receiver.example.com", "tok")
        assert await submitter.connect() is False

    @pytest.mark.asyncio
    async def test_connect_swallows_exception_and_returns_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Connect swallows exception and returns false."""

        def _boom(*a: Any, **k: Any) -> Any:
            """Boom."""
            raise RuntimeError("dns failure")

        monkeypatch.setattr(httpx, "AsyncClient", _boom)
        submitter = RESTSubmitter("https://receiver.example.com", "tok")
        assert await submitter.connect() is False


class TestRESTSubmitterHealthCheck:
    """R E S T Submitter Health Check."""

    @pytest.mark.asyncio
    async def test_no_client_is_unhealthy(self) -> None:
        """No client is unhealthy."""
        submitter = RESTSubmitter("https://receiver.example.com", "tok")
        assert await submitter.health_check() is False

    @pytest.mark.asyncio
    async def test_request_error_is_unhealthy(self) -> None:
        """Request error is unhealthy."""
        submitter = RESTSubmitter("https://receiver.example.com", "tok")
        submitter.client = _FakeAsyncClient(get_response=httpx.RequestError("timed out"))  # type: ignore[assignment]
        assert await submitter.health_check() is False


class TestRESTSubmitterSubmitLogs:
    """R E S T Submitter Submit Logs."""

    @pytest.mark.asyncio
    async def test_no_client_raises_connection_error(self) -> None:
        """No client raises connection error."""
        submitter = RESTSubmitter("https://receiver.example.com", "tok")
        with pytest.raises(ReceiverConnectionError):
            await submitter.submit_logs([{"msg": "hi"}])

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        """Success."""
        submitter = RESTSubmitter("https://receiver.example.com", "tok")
        submitter.client = _FakeAsyncClient(post_response=_FakeResponse(200))  # type: ignore[assignment]
        assert await submitter.submit_logs([{"msg": "hi"}]) is True

    @pytest.mark.asyncio
    async def test_401_raises_submission_error_naming_auth(self) -> None:
        """401 raises submission error naming auth."""
        submitter = RESTSubmitter("https://receiver.example.com", "tok")
        submitter.client = _FakeAsyncClient(post_response=_FakeResponse(401))  # type: ignore[assignment]
        with pytest.raises(SubmissionError, match="Authentication failed"):
            await submitter.submit_logs([{"msg": "hi"}])

    @pytest.mark.asyncio
    async def test_other_status_raises_submission_error_with_status(self) -> None:
        """Other status raises submission error with status."""
        submitter = RESTSubmitter("https://receiver.example.com", "tok")
        submitter.client = _FakeAsyncClient(post_response=_FakeResponse(500, text="boom"))  # type: ignore[assignment]
        with pytest.raises(SubmissionError, match="500"):
            await submitter.submit_logs([{"msg": "hi"}])

    @pytest.mark.asyncio
    async def test_request_error_raises_submission_error(self) -> None:
        """Request error raises submission error."""
        submitter = RESTSubmitter("https://receiver.example.com", "tok")
        submitter.client = _FakeAsyncClient(post_response=httpx.RequestError("reset"))  # type: ignore[assignment]
        with pytest.raises(SubmissionError, match="reset"):
            await submitter.submit_logs([{"msg": "hi"}])


class TestRESTSubmitterSubmitMetrics:
    """R E S T Submitter Submit Metrics."""

    @pytest.mark.asyncio
    async def test_no_client_raises_connection_error(self) -> None:
        """No client raises connection error."""
        submitter = RESTSubmitter("https://receiver.example.com", "tok")
        with pytest.raises(ReceiverConnectionError):
            await submitter.submit_metrics([{"name": "x"}])

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        """Success."""
        submitter = RESTSubmitter("https://receiver.example.com", "tok")
        submitter.client = _FakeAsyncClient(post_response=_FakeResponse(200))  # type: ignore[assignment]
        assert await submitter.submit_metrics([{"name": "x"}]) is True

    @pytest.mark.asyncio
    async def test_401_raises_submission_error(self) -> None:
        """401 raises submission error."""
        submitter = RESTSubmitter("https://receiver.example.com", "tok")
        submitter.client = _FakeAsyncClient(post_response=_FakeResponse(401))  # type: ignore[assignment]
        with pytest.raises(SubmissionError, match="Authentication failed"):
            await submitter.submit_metrics([{"name": "x"}])

    @pytest.mark.asyncio
    async def test_request_error_raises_submission_error(self) -> None:
        """Request error raises submission error."""
        submitter = RESTSubmitter("https://receiver.example.com", "tok")
        submitter.client = _FakeAsyncClient(post_response=httpx.RequestError("reset"))  # type: ignore[assignment]
        with pytest.raises(SubmissionError):
            await submitter.submit_metrics([{"name": "x"}])

    @pytest.mark.asyncio
    async def test_other_status_raises_submission_error_with_status(self) -> None:
        """Other status raises submission error with status."""
        submitter = RESTSubmitter("https://receiver.example.com", "tok")
        submitter.client = _FakeAsyncClient(post_response=_FakeResponse(500, text="boom"))  # type: ignore[assignment]
        with pytest.raises(SubmissionError, match="500"):
            await submitter.submit_metrics([{"name": "x"}])


class TestRESTSubmitterLifecycle:
    """R E S T Submitter Lifecycle."""

    @pytest.mark.asyncio
    async def test_disconnect_with_no_client_is_a_noop(self) -> None:
        """Disconnect with no client is a noop."""
        submitter = RESTSubmitter("https://receiver.example.com", "tok")
        await submitter.disconnect()  # must not raise

    @pytest.mark.asyncio
    async def test_disconnect_closes_client(self) -> None:
        """Disconnect closes client."""
        submitter = RESTSubmitter("https://receiver.example.com", "tok")
        fake = _FakeAsyncClient()
        submitter.client = fake  # type: ignore[assignment]
        await submitter.disconnect()
        assert fake.closed is True

    @pytest.mark.asyncio
    async def test_context_manager_connects_and_disconnects(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Context manager connects and disconnects."""
        created: list[_FakeAsyncClient] = []

        def _factory(*a: Any, **k: Any) -> _FakeAsyncClient:
            """Factory."""
            fake = _FakeAsyncClient(*a, get_response=_FakeResponse(200), **k)
            created.append(fake)
            return fake

        monkeypatch.setattr(httpx, "AsyncClient", _factory)
        async with RESTSubmitter("https://receiver.example.com", "tok") as submitter:
            assert submitter.client is not None
        assert created[0].closed is True


class TestGRPCSubmitterConnect:
    """G R P C Submitter Connect."""

    def test_connect_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Connect success."""
        monkeypatch.setattr(grpc, "ssl_channel_credentials", lambda: object())
        monkeypatch.setattr(grpc, "secure_channel", lambda url, creds: _FakeChannel())
        monkeypatch.setattr(grpc, "channel_ready_future", lambda channel: _FakeReadyFuture("ready"))
        submitter = GRPCSubmitter("receiver.example.com:50051", "tok")
        assert submitter.connect() is True
        assert submitter._connected is True

    def test_connect_unhealthy_channel_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Connect unhealthy channel returns false."""
        monkeypatch.setattr(grpc, "ssl_channel_credentials", lambda: object())
        monkeypatch.setattr(grpc, "secure_channel", lambda url, creds: _FakeChannel())
        monkeypatch.setattr(
            grpc, "channel_ready_future", lambda channel: _FakeReadyFuture("timeout")
        )
        submitter = GRPCSubmitter("receiver.example.com:50051", "tok")
        assert submitter.connect() is False
        assert submitter._connected is False

    def test_connect_rpc_error_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Connect rpc error returns false."""

        def _boom(*a: Any, **k: Any) -> Any:
            """Boom."""
            raise _FakeRpcError()

        monkeypatch.setattr(grpc, "ssl_channel_credentials", lambda: object())
        monkeypatch.setattr(grpc, "secure_channel", _boom)
        submitter = GRPCSubmitter("receiver.example.com:50051", "tok")
        assert submitter.connect() is False


class TestGRPCSubmitterHealthCheck:
    """G R P C Submitter Health Check."""

    def test_no_channel_is_unhealthy(self) -> None:
        """No channel is unhealthy."""
        submitter = GRPCSubmitter("receiver.example.com:50051", "tok")
        assert submitter.health_check() is False

    def test_timeout_is_unhealthy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Timeout is unhealthy."""
        submitter = GRPCSubmitter("receiver.example.com:50051", "tok")
        submitter.channel = _FakeChannel()
        monkeypatch.setattr(
            grpc, "channel_ready_future", lambda channel: _FakeReadyFuture("timeout")
        )
        assert submitter.health_check() is False

    def test_other_exception_is_unhealthy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Other exception is unhealthy."""
        submitter = GRPCSubmitter("receiver.example.com:50051", "tok")
        submitter.channel = _FakeChannel()

        def _boom(channel: Any) -> Any:
            """Boom."""
            raise RuntimeError("boom")

        monkeypatch.setattr(grpc, "channel_ready_future", _boom)
        assert submitter.health_check() is False


class TestGRPCSubmitterSubmit:
    """G R P C Submitter Submit."""

    def test_submit_logs_not_connected_raises_connection_error(self) -> None:
        """Submit logs not connected raises connection error."""
        submitter = GRPCSubmitter("receiver.example.com:50051", "tok")
        with pytest.raises(ReceiverConnectionError):
            submitter.submit_logs([{"msg": "hi"}])

    def test_submit_logs_success(self) -> None:
        """Submit logs success."""
        submitter = GRPCSubmitter("receiver.example.com:50051", "tok")
        submitter._connected = True
        assert submitter.submit_logs([{"msg": "hi"}]) is True

    def test_submit_metrics_not_connected_raises_connection_error(self) -> None:
        """Submit metrics not connected raises connection error."""
        submitter = GRPCSubmitter("receiver.example.com:50051", "tok")
        with pytest.raises(ReceiverConnectionError):
            submitter.submit_metrics([{"name": "x"}])

    def test_submit_metrics_success(self) -> None:
        """Submit metrics success."""
        submitter = GRPCSubmitter("receiver.example.com:50051", "tok")
        submitter._connected = True
        assert submitter.submit_metrics([{"name": "x"}]) is True

    def test_submit_logs_rpc_error_raises_submission_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Submit logs rpc error raises submission error."""
        submitter = GRPCSubmitter("receiver.example.com:50051", "tok")
        submitter._connected = True
        # The real gRPC call isn't wired up yet (see the module's own TODO
        # -- no compiled stub exists), so the only statement inside the try
        # block that can raise is the logger.info() success log. Forcing it
        # to raise grpc.RpcError is the only way to reach the except branch
        # as the code is actually structured today.
        monkeypatch.setattr(
            "app.killkrill_client.grpc_client.logger.info",
            lambda *a, **k: (_ for _ in ()).throw(_FakeRpcError(details="log submission rejected")),
        )
        with pytest.raises(SubmissionError, match="log submission rejected"):
            submitter.submit_logs([{"msg": "hi"}])

    def test_submit_metrics_rpc_error_raises_submission_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Submit metrics rpc error raises submission error."""
        submitter = GRPCSubmitter("receiver.example.com:50051", "tok")
        submitter._connected = True
        monkeypatch.setattr(
            "app.killkrill_client.grpc_client.logger.info",
            lambda *a, **k: (_ for _ in ()).throw(_FakeRpcError(details="metrics rejected")),
        )
        with pytest.raises(SubmissionError, match="metrics rejected"):
            submitter.submit_metrics([{"name": "x"}])

    def test_disconnect_closes_channel(self) -> None:
        """Disconnect closes channel."""
        submitter = GRPCSubmitter("receiver.example.com:50051", "tok")
        fake_channel = _FakeChannel()
        submitter.channel = fake_channel
        submitter._connected = True
        submitter.disconnect()
        assert fake_channel.closed is True
        assert submitter._connected is False

    def test_disconnect_with_no_channel_is_a_noop(self) -> None:
        """Disconnect with no channel is a noop."""
        submitter = GRPCSubmitter("receiver.example.com:50051", "tok")
        submitter.disconnect()  # must not raise

    def test_context_manager_connects_and_disconnects(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Context manager connects and disconnects."""
        monkeypatch.setattr(grpc, "ssl_channel_credentials", lambda: object())
        fake_channel = _FakeChannel()
        monkeypatch.setattr(grpc, "secure_channel", lambda url, creds: fake_channel)
        monkeypatch.setattr(grpc, "channel_ready_future", lambda channel: _FakeReadyFuture("ready"))
        with GRPCSubmitter("receiver.example.com:50051", "tok") as submitter:
            assert submitter._connected is True
        assert fake_channel.closed is True


def _auth_success_client_factory(
    *, access_token: str = "at1", refresh_token: str = "rt1", expires_in: int = 3600
) -> Any:
    """Auth success client factory."""

    def _factory(*a: Any, **k: Any) -> _FakeAsyncClient:
        """Factory."""
        return _FakeAsyncClient(
            *a,
            post_response=_FakeResponse(
                200,
                {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "expires_in": expires_in,
                },
            ),
            **k,
        )

    return _factory


class TestReceiverClientAuthenticate:
    """Receiver Client Authenticate."""

    @pytest.mark.asyncio
    async def test_success_initializes_grpc_first(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Success initializes grpc first."""
        monkeypatch.setattr(httpx, "AsyncClient", _auth_success_client_factory())
        monkeypatch.setattr(grpc, "ssl_channel_credentials", lambda: object())
        monkeypatch.setattr(grpc, "secure_channel", lambda url, creds: _FakeChannel())
        monkeypatch.setattr(grpc, "channel_ready_future", lambda channel: _FakeReadyFuture("ready"))

        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        assert await client.authenticate() is True
        assert client._authenticated is True
        assert client.token_info is not None
        assert client.token_info.access_token == "at1"
        assert client.use_grpc is True
        assert client.grpc_client is not None

    @pytest.mark.asyncio
    async def test_falls_back_to_rest_when_grpc_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Falls back to rest when grpc unavailable."""
        monkeypatch.setattr(httpx, "AsyncClient", _auth_success_client_factory())
        monkeypatch.setattr(grpc, "ssl_channel_credentials", lambda: object())

        def _boom(*a: Any, **k: Any) -> Any:
            """Boom."""
            raise _FakeRpcError()

        monkeypatch.setattr(grpc, "secure_channel", _boom)

        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        assert await client.authenticate() is True
        assert client.use_grpc is False
        assert client.rest_client is not None

    @pytest.mark.asyncio
    async def test_non_200_raises_authentication_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non 200 raises authentication error."""
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda *a, **k: _FakeAsyncClient(
                *a, post_response=_FakeResponse(403, text="denied"), **k
            ),
        )
        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        with pytest.raises(AuthenticationError, match="403"):
            await client.authenticate()
        assert client._authenticated is False

    @pytest.mark.asyncio
    async def test_request_error_raises_authentication_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Request error raises authentication error."""
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda *a, **k: _FakeAsyncClient(*a, post_response=httpx.RequestError("refused"), **k),
        )
        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        with pytest.raises(AuthenticationError, match="refused"):
            await client.authenticate()

    @pytest.mark.asyncio
    async def test_missing_field_in_response_raises_authentication_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 200 with no access_token key -> KeyError inside the try block.
        """Missing field in response raises authentication error."""
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda *a, **k: _FakeAsyncClient(*a, post_response=_FakeResponse(200, {}), **k),
        )
        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        with pytest.raises(AuthenticationError, match="Invalid authentication response"):
            await client.authenticate()


class TestReceiverClientRefreshToken:
    """Receiver Client Refresh Token."""

    @pytest.mark.asyncio
    async def test_no_token_raises_authentication_error(self) -> None:
        """No token raises authentication error."""
        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        with pytest.raises(AuthenticationError, match="No token to refresh"):
            await client.refresh_token()

    @pytest.mark.asyncio
    async def test_success_updates_access_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Success updates access token."""
        from datetime import UTC, datetime, timedelta

        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        client.token_info = TokenInfo(
            access_token="stale",
            refresh_token="rt1",
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=1),
        )
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda *a, **k: _FakeAsyncClient(
                *a,
                post_response=_FakeResponse(200, {"access_token": "fresh", "expires_in": 3600}),
                **k,
            ),
        )
        monkeypatch.setattr(grpc, "ssl_channel_credentials", lambda: object())
        monkeypatch.setattr(grpc, "secure_channel", lambda url, creds: _FakeChannel())
        monkeypatch.setattr(grpc, "channel_ready_future", lambda channel: _FakeReadyFuture("ready"))

        assert await client.refresh_token() is True
        assert client.token_info.access_token == "fresh"

    @pytest.mark.asyncio
    async def test_non_200_reauthenticates_instead_of_raising(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non 200 reauthenticates instead of raising."""
        from datetime import UTC, datetime, timedelta

        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        client.token_info = TokenInfo(
            access_token="stale",
            refresh_token="rt1",
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=1),
        )
        # Refresh POST fails (401); authenticate's POST (called as the
        # fallback) succeeds -- both share the same faked AsyncClient, so
        # distinguish by whichever a single canned response satisfies:
        # refresh_token treats ANY non-200 as "re-authenticate", and
        # authenticate() then re-POSTs and gets the same canned response.
        # A 401 fails refresh's check and would also fail authenticate's
        # 200 check, so route to `authenticate` explicitly via monkeypatch.
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda *a, **k: _FakeAsyncClient(*a, post_response=_FakeResponse(401), **k),
        )
        reauthenticated = AsyncMock(return_value=True)
        monkeypatch.setattr(client, "authenticate", reauthenticated)

        assert await client.refresh_token() is True
        reauthenticated.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_request_error_raises_authentication_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Request error raises authentication error."""
        from datetime import UTC, datetime, timedelta

        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        client.token_info = TokenInfo(
            access_token="stale",
            refresh_token="rt1",
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=1),
        )
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda *a, **k: _FakeAsyncClient(*a, post_response=httpx.RequestError("reset"), **k),
        )
        with pytest.raises(AuthenticationError, match="Token refresh failed"):
            await client.refresh_token()


class TestReceiverClientEnsureAuthenticated:
    """Receiver Client Ensure Authenticated."""

    @pytest.mark.asyncio
    async def test_not_authenticated_calls_authenticate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Not authenticated calls authenticate."""
        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        authenticate = AsyncMock(return_value=True)
        monkeypatch.setattr(client, "authenticate", authenticate)

        await client._ensure_authenticated()
        authenticate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_expired_token_calls_refresh(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Expired token calls refresh."""
        from datetime import UTC, datetime, timedelta

        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        client._authenticated = True
        client.token_info = TokenInfo(
            access_token="a",
            refresh_token="r",
            expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1),
        )
        refresh = AsyncMock(return_value=True)
        monkeypatch.setattr(client, "refresh_token", refresh)

        await client._ensure_authenticated()
        refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_valid_token_calls_neither(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Valid token calls neither."""
        from datetime import UTC, datetime, timedelta

        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        client._authenticated = True
        client.token_info = TokenInfo(
            access_token="a",
            refresh_token="r",
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
        )
        authenticate = AsyncMock(return_value=True)
        refresh = AsyncMock(return_value=True)
        monkeypatch.setattr(client, "authenticate", authenticate)
        monkeypatch.setattr(client, "refresh_token", refresh)

        await client._ensure_authenticated()
        authenticate.assert_not_called()
        refresh.assert_not_called()


class TestReceiverClientSubmitAndRetry:
    """Receiver Client Submit And Retry."""

    @pytest.mark.asyncio
    async def test_submit_logs_no_active_client_raises_connection_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Submit logs no active client raises connection error."""
        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        monkeypatch.setattr(client, "_ensure_authenticated", AsyncMock(return_value=None))
        client.use_grpc = False
        client.rest_client = None
        client.grpc_client = None

        # ConnectionError is not caught by _retry_with_backoff's `except
        # SubmissionError` -- it propagates on the first attempt, no retry.
        with pytest.raises(ReceiverConnectionError):
            await client.submit_logs([{"msg": "hi"}])

    @pytest.mark.asyncio
    async def test_submit_logs_via_grpc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Submit logs via grpc."""
        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        monkeypatch.setattr(client, "_ensure_authenticated", AsyncMock(return_value=None))
        client.use_grpc = True
        client.grpc_client = GRPCSubmitter("grpc.example.com:50051", "tok")
        client.grpc_client._connected = True

        assert await client.submit_logs([{"msg": "hi"}]) is True

    @pytest.mark.asyncio
    async def test_submit_metrics_via_rest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Submit metrics via rest."""
        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        monkeypatch.setattr(client, "_ensure_authenticated", AsyncMock(return_value=None))
        client.use_grpc = False
        rest = RESTSubmitter("https://api.example.com", "tok")
        rest.client = _FakeAsyncClient(post_response=_FakeResponse(200))  # type: ignore[assignment]
        client.rest_client = rest

        assert await client.submit_metrics([{"name": "x"}]) is True

    @pytest.mark.asyncio
    async def test_retries_then_succeeds_after_grpc_failure_falls_back_to_rest(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A gRPC SubmissionError triggers backoff + protocol fallback to REST.

        Distinguishes the retry path from a bare success: the second
        attempt must actually go through the REST client the fallback
        installed, not the gRPC client that just failed.
        """
        client = ReceiverClient(
            "https://api.example.com",
            "grpc.example.com:50051",
            "cid",
            "sec",
            max_retries=2,
            retry_backoff=0.0,
        )
        monkeypatch.setattr(client, "_ensure_authenticated", AsyncMock(return_value=None))
        monkeypatch.setattr("app.killkrill_client.client.asyncio.sleep", AsyncMock())

        client.use_grpc = True
        failing_grpc = GRPCSubmitter("grpc.example.com:50051", "tok")
        failing_grpc._connected = True
        monkeypatch.setattr(
            failing_grpc,
            "submit_logs",
            lambda logs: (_ for _ in ()).throw(SubmissionError("grpc down")),
        )
        client.grpc_client = failing_grpc

        working_rest = RESTSubmitter("https://api.example.com", "tok")
        working_rest.client = _FakeAsyncClient(post_response=_FakeResponse(200))  # type: ignore[assignment]

        async def _fake_fallback() -> None:
            """Fake fallback."""
            client.use_grpc = False
            client.rest_client = working_rest

        monkeypatch.setattr(client, "_fallback_to_rest", _fake_fallback)

        assert await client.submit_logs([{"msg": "hi"}]) is True

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_raises_submission_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All retries exhausted raises submission error."""
        client = ReceiverClient(
            "https://api.example.com",
            "grpc.example.com:50051",
            "cid",
            "sec",
            max_retries=2,
            retry_backoff=0.0,
        )
        monkeypatch.setattr(client, "_ensure_authenticated", AsyncMock(return_value=None))
        monkeypatch.setattr("app.killkrill_client.client.asyncio.sleep", AsyncMock())
        monkeypatch.setattr(client, "_fallback_to_rest", AsyncMock())

        client.use_grpc = True
        always_fails = GRPCSubmitter("grpc.example.com:50051", "tok")
        always_fails._connected = True
        monkeypatch.setattr(
            always_fails,
            "submit_logs",
            lambda logs: (_ for _ in ()).throw(SubmissionError("still down")),
        )
        client.grpc_client = always_fails

        with pytest.raises(SubmissionError, match="submit_logs failed after 2 retries"):
            await client.submit_logs([{"msg": "hi"}])


class TestReceiverClientHealthCheck:
    """Receiver Client Health Check."""

    @pytest.mark.asyncio
    async def test_no_active_client_is_unhealthy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No active client is unhealthy."""
        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        monkeypatch.setattr(client, "_ensure_authenticated", AsyncMock(return_value=None))
        assert await client.health_check() is False

    @pytest.mark.asyncio
    async def test_healthy_via_grpc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Healthy via grpc."""
        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        monkeypatch.setattr(client, "_ensure_authenticated", AsyncMock(return_value=None))
        client.use_grpc = True
        healthy_grpc = GRPCSubmitter("grpc.example.com:50051", "tok")
        healthy_grpc.channel = _FakeChannel()
        monkeypatch.setattr(grpc, "channel_ready_future", lambda channel: _FakeReadyFuture("ready"))
        client.grpc_client = healthy_grpc

        assert await client.health_check() is True

    @pytest.mark.asyncio
    async def test_exception_during_check_is_unhealthy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exception during check is unhealthy."""
        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")

        async def _boom() -> None:
            """Boom."""
            raise RuntimeError("boom")

        monkeypatch.setattr(client, "_ensure_authenticated", _boom)
        assert await client.health_check() is False


class TestReceiverClientLifecycle:
    """Receiver Client Lifecycle."""

    @pytest.mark.asyncio
    async def test_close_disconnects_both_clients(self) -> None:
        """Close disconnects both clients."""
        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        client._authenticated = True
        grpc_sub = GRPCSubmitter("grpc.example.com:50051", "tok")
        grpc_sub.channel = _FakeChannel()
        grpc_sub._connected = True
        client.grpc_client = grpc_sub

        rest_sub = RESTSubmitter("https://api.example.com", "tok")
        fake_http = _FakeAsyncClient()
        rest_sub.client = fake_http  # type: ignore[assignment]
        client.rest_client = rest_sub

        await client.close()

        assert grpc_sub._connected is False
        assert fake_http.closed is True
        assert client._authenticated is False

    @pytest.mark.asyncio
    async def test_async_context_manager_authenticates_and_closes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Async context manager authenticates and closes."""
        monkeypatch.setattr(httpx, "AsyncClient", _auth_success_client_factory())
        monkeypatch.setattr(grpc, "ssl_channel_credentials", lambda: object())
        monkeypatch.setattr(grpc, "secure_channel", lambda url, creds: _FakeChannel())
        monkeypatch.setattr(grpc, "channel_ready_future", lambda channel: _FakeReadyFuture("ready"))

        async with ReceiverClient(
            "https://api.example.com", "grpc.example.com:50051", "cid", "sec"
        ) as client:
            assert client._authenticated is True

        assert client._authenticated is False


class TestInitializeClientsClosesExisting:
    """Initialize Clients Closes Existing."""

    @pytest.mark.asyncio
    async def test_disconnects_both_existing_clients_before_reinit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A token refresh must close the OLD protocol clients, not leak them."""
        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        client.token_info = TokenInfo(access_token="a", refresh_token="r", expires_at=datetime.max)

        stale_grpc = GRPCSubmitter("grpc.example.com:50051", "tok")
        stale_grpc.channel = _FakeChannel()
        stale_grpc._connected = True
        client.grpc_client = stale_grpc

        stale_rest = RESTSubmitter("https://api.example.com", "tok")
        stale_fake_http = _FakeAsyncClient()
        stale_rest.client = stale_fake_http  # type: ignore[assignment]
        client.rest_client = stale_rest

        monkeypatch.setattr(client, "_try_grpc", AsyncMock(return_value=False))
        monkeypatch.setattr(client, "_fallback_to_rest", AsyncMock())

        await client._initialize_clients()

        assert stale_grpc._connected is False
        assert stale_fake_http.closed is True

    @pytest.mark.asyncio
    async def test_try_grpc_swallows_unexpected_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Try grpc swallows unexpected exception."""
        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        client.token_info = TokenInfo(access_token="a", refresh_token="r", expires_at=datetime.max)

        def _boom(*a: Any, **k: Any) -> Any:
            """Boom."""
            raise RuntimeError("unexpected wiring failure")

        monkeypatch.setattr("app.killkrill_client.client.GRPCSubmitter", _boom)
        assert await client._try_grpc() is False


class TestReceiverClientSubmitViaGrpcAndConnectionError:
    """Receiver Client Submit Via Grpc And Connection Error."""

    @pytest.mark.asyncio
    async def test_submit_metrics_via_grpc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Submit metrics via grpc."""
        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        monkeypatch.setattr(client, "_ensure_authenticated", AsyncMock(return_value=None))
        client.use_grpc = True
        healthy_grpc = GRPCSubmitter("grpc.example.com:50051", "tok")
        healthy_grpc._connected = True
        client.grpc_client = healthy_grpc

        assert await client.submit_metrics([{"name": "x"}]) is True

    @pytest.mark.asyncio
    async def test_submit_metrics_no_active_client_raises_connection_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Submit metrics no active client raises connection error."""
        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        monkeypatch.setattr(client, "_ensure_authenticated", AsyncMock(return_value=None))
        client.use_grpc = False
        client.rest_client = None
        client.grpc_client = None

        with pytest.raises(ReceiverConnectionError):
            await client.submit_metrics([{"name": "x"}])

    @pytest.mark.asyncio
    async def test_health_check_via_rest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Health check via rest."""
        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        monkeypatch.setattr(client, "_ensure_authenticated", AsyncMock(return_value=None))
        client.use_grpc = False
        rest = RESTSubmitter("https://api.example.com", "tok")
        rest.client = _FakeAsyncClient(get_response=_FakeResponse(200))  # type: ignore[assignment]
        client.rest_client = rest

        assert await client.health_check() is True


class TestInitializeClientsNoToken:
    """Initialize Clients No Token."""

    @pytest.mark.asyncio
    async def test_returns_early_without_token_info(self) -> None:
        """Returns early without token info."""
        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        assert client.token_info is None
        await client._initialize_clients()  # must not raise
        assert client.grpc_client is None
        assert client.rest_client is None

    @pytest.mark.asyncio
    async def test_try_grpc_without_token_returns_false(self) -> None:
        """Try grpc without token returns false."""
        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        assert await client._try_grpc() is False

    @pytest.mark.asyncio
    async def test_fallback_to_rest_without_token_is_a_noop(self) -> None:
        """Fallback to rest without token is a noop."""
        client = ReceiverClient("https://api.example.com", "grpc.example.com:50051", "cid", "sec")
        await client._fallback_to_rest()
        assert client.rest_client is None
