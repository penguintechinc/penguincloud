"""SMTP delivery for password-reset tokens (the second half of the fix).

A prior security fix closed the token-leak in ``/api/v1/auth/forgot-
password``: the token stopped being returned to the caller. That left the
endpoint secure but the feature unfinished — ``_deliver_password_reset_token``
generated and stored a token, then logged that it had nowhere to go. A user
who clicked "forgot password" always saw success and no email ever arrived.
This module tests the SMTP transport that closes that gap.

Two requirements pull against each other, and both are asserted here,
independently, on every relevant test:

* ``forgot_password``'s HTTP response must be identical — always
  ``PASSWORD_RESET_ACK``, 200 — whether the address exists, delivery
  succeeds, or delivery fails. Anything that changed the caller-visible
  outcome on an SMTP failure would turn "the transport just broke" into a
  second, narrower account-enumeration oracle.
* An unconfigured or failing transport must fail LOUDLY to the operator —
  via the existing ``PASSWORD_RESET_DELIVERY_ERRORS_COUNTER`` (same
  Prometheus-counter pattern as ``health_poller.POLL_ERRORS_COUNTER``, see
  test_health_poller.py) and a structured ERROR log call.

Why a recording logger fake, not ``caplog``
============================================
``app.auth``'s ``log`` is built via ``penguintechinc_utils.logging.
get_logger``, i.e. structlog. Nothing in this service ever calls
``configure_logging()`` (grepped: no call site), so structlog falls back to
its own default logger factory, which prints directly and is never routed
through Python's stdlib ``logging`` handler chain — the chain ``caplog``
attaches to. A ``caplog.at_level(...)`` assertion here would pass
vacuously (zero records captured) regardless of what was actually logged,
which is exactly the "writing the test does not mean it can fail" trap.
Patching ``app.auth.log`` with a fake that records every call's raw
arguments tests the thing this module actually controls: what auth.py
passes to the logger, independent of how any future logging configuration
renders it.
"""

from __future__ import annotations

import smtplib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app import auth
from quart import Quart

PASSWORD = "resetdeliverytest123"


class _RecordingLogger:
    """Fake structlog BoundLogger: records event name + kwargs per call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def warning(self, event: str, **kwargs: Any) -> None:
        self.calls.append(("warning", event, kwargs))

    def error(self, event: str, **kwargs: Any) -> None:
        self.calls.append(("error", event, kwargs))

    def info(self, event: str, **kwargs: Any) -> None:
        self.calls.append(("info", event, kwargs))

    def blob(self) -> str:
        """Every call, fully stringified — what a "never appears" check scans."""
        return str(self.calls)


class _FakeSMTP:
    """Records what would have gone over the wire; no real socket ever opens."""

    def __init__(self, host: str, port: int, timeout: float | None = None) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.starttls_called = False
        self.login_calls: list[tuple[str, str]] = []
        self.sent_messages: list[Any] = []

    def __enter__(self) -> _FakeSMTP:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        return None

    def starttls(self, context: Any = None) -> None:
        self.starttls_called = True

    def login(self, username: str, password: str) -> None:
        self.login_calls.append((username, password))

    def send_message(self, message: Any) -> None:
        self.sent_messages.append(message)


class _RefusingFakeSMTP(_FakeSMTP):
    """Simulates smtplib raising — the recipient address lands in the exception."""

    def send_message(self, message: Any) -> None:
        raise smtplib.SMTPRecipientsRefused({message["To"]: (550, b"mailbox unavailable")})


async def _register(client: Any, **overrides: Any) -> tuple[str, Any]:
    email = overrides.pop("email", f"resetdel-{uuid.uuid4().hex[:8]}@example.com")
    payload = {"email": email, "password": PASSWORD, "full_name": "Reset Delivery Test"}
    payload.update(overrides)
    return email, await client.post("/api/v1/auth/register", json=payload)


@pytest.mark.asyncio
class TestUnconfiguredTransport:
    """SMTP_HOST unset — the state this service shipped in before Job 2."""

    async def test_caller_still_gets_the_generic_ack(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The HTTP response must not change when delivery cannot happen."""
        monkeypatch.delenv("SMTP_HOST", raising=False)
        email, register = await _register(client)
        assert register.status_code == 201

        response = await client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert response.status_code == 200
        assert (await response.get_json()) == auth.PASSWORD_RESET_ACK

    async def test_operator_is_told_loudly(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Not configured must not read as success to anyone watching metrics/logs."""
        monkeypatch.delenv("SMTP_HOST", raising=False)
        fake_log = _RecordingLogger()
        monkeypatch.setattr(auth, "log", fake_log)

        before = auth.PASSWORD_RESET_DELIVERY_ERRORS_COUNTER.labels(
            reason="unconfigured"
        )._value.get()

        async with app.app_context():
            await auth._deliver_password_reset_token(
                user_id=1,
                email="watched@example.com",
                token="unconfigured-path-token",  # noqa: S106 -- synthetic marker, not a secret
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )

        after = auth.PASSWORD_RESET_DELIVERY_ERRORS_COUNTER.labels(
            reason="unconfigured"
        )._value.get()
        assert after == before + 1

        assert len(fake_log.calls) == 1
        level, event, kwargs = fake_log.calls[0]
        assert level == "error"
        assert event == "password_reset_token_undeliverable"
        assert kwargs["extra"]["user_id"] == 1


@pytest.mark.asyncio
class TestConfiguredTransport:
    """A working SMTP relay — delivery actually happens."""

    async def test_token_is_delivered_exactly_once(
        self,
        client: Any,
        app: Quart,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A configured relay actually sends, with STARTTLS and auth."""
        monkeypatch.setenv("SMTP_HOST", "smtp.example.internal")
        monkeypatch.setenv("SMTP_PORT", "587")
        monkeypatch.setenv("SMTP_USERNAME", "portal")
        monkeypatch.setenv("SMTP_PASSWORD", "not-a-real-secret")  # noqa: S105

        sent: list[_FakeSMTP] = []

        def _fake_smtp_ctor(host: str, port: int, timeout: float | None = None) -> _FakeSMTP:
            instance = _FakeSMTP(host, port, timeout)
            sent.append(instance)
            return instance

        monkeypatch.setattr("app.auth.smtplib.SMTP", _fake_smtp_ctor)

        email, register = await _register(client)
        assert register.status_code == 201

        response = await client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert response.status_code == 200
        assert (await response.get_json()) == auth.PASSWORD_RESET_ACK

        assert len(sent) == 1, "delivery must be attempted exactly once"
        transport = sent[0]
        assert transport.host == "smtp.example.internal"
        assert transport.starttls_called, "STARTTLS must be used by default (security.md)"
        assert transport.login_calls == [("portal", "not-a-real-secret")]
        assert len(transport.sent_messages) == 1
        message = transport.sent_messages[0]
        assert message["To"] == email
        # The real token DID reach the transport -- this is delivery, not a
        # second place it must be scrubbed from (see TestNoLeakage below for
        # the log-side guarantee).
        body = message.get_content()
        assert "reset-password?token=" in body

    async def test_smtp_failure_does_not_change_the_response_but_is_counted(
        self,
        client: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A refused recipient must not surface as anything but the generic ACK."""
        monkeypatch.setenv("SMTP_HOST", "smtp.example.internal")
        monkeypatch.setenv("SMTP_USE_TLS", "false")
        monkeypatch.setattr("app.auth.smtplib.SMTP", _RefusingFakeSMTP)

        fake_log = _RecordingLogger()
        monkeypatch.setattr(auth, "log", fake_log)

        before = auth.PASSWORD_RESET_DELIVERY_ERRORS_COUNTER.labels(
            reason="smtp_error"
        )._value.get()

        email, register = await _register(client)
        assert register.status_code == 201

        response = await client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert response.status_code == 200
        assert (await response.get_json()) == auth.PASSWORD_RESET_ACK

        after = auth.PASSWORD_RESET_DELIVERY_ERRORS_COUNTER.labels(reason="smtp_error")._value.get()
        assert after == before + 1

        error_calls = [c for c in fake_log.calls if c[0] == "error"]
        assert len(error_calls) == 1
        assert error_calls[0][1] == "password_reset_token_delivery_failed"
        # Only the exception's TYPE name, never its message -- smtplib
        # exceptions like SMTPRecipientsRefused embed the recipient address
        # in their own arguments.
        assert error_calls[0][2]["extra"]["error_type"] == "SMTPRecipientsRefused"
        assert email not in fake_log.blob()


@pytest.mark.asyncio
class TestNoLeakage:
    """The token and the recipient's email must never reach a log call."""

    async def test_token_and_email_absent_from_every_log_call_on_success(
        self,
        client: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A successful delivery logs nothing that identifies the recipient."""
        monkeypatch.setenv("SMTP_HOST", "smtp.example.internal")
        monkeypatch.setattr("app.auth.smtplib.SMTP", _FakeSMTP)

        fake_log = _RecordingLogger()
        monkeypatch.setattr(auth, "log", fake_log)

        email, register = await _register(client)
        assert register.status_code == 201

        response = await client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert response.status_code == 200

        # No error/warning on the happy path, and — the actual guarantee —
        # nothing logged anywhere carries the address.
        assert email not in fake_log.blob()

    async def test_token_absent_from_every_log_call_when_unconfigured(
        self,
        app: Quart,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The undeliverable-path log call carries neither token nor email."""
        monkeypatch.delenv("SMTP_HOST", raising=False)
        fake_log = _RecordingLogger()
        monkeypatch.setattr(auth, "log", fake_log)

        secret_token = f"do-not-log-me-{uuid.uuid4().hex}"  # noqa: S105

        async with app.app_context():
            await auth._deliver_password_reset_token(
                user_id=42,
                email="someone-private@example.com",
                token=secret_token,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )

        blob = fake_log.blob()
        assert secret_token not in blob
        assert "someone-private@example.com" not in blob
