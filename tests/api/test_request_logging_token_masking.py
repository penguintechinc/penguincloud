"""Regression coverage for middleware.setup_request_logging's token masking.

app/middleware.py's after_request hook logs request.path verbatim to
killkrill_manager via its ECS-format `log()` call. Two routes carry a
single-use bearer credential as a URL path segment rather than a body
field -- POST /api/v1/teams/invitations/<token>/accept and POST
/api/v1/auth/confirm-email/<token> -- so before the fix/team-invitations
masking change, every call to either route wrote that token to the access
log in plaintext. Nothing exercised that logging path at all before this
file: the fix landed with no test able to catch its own regression -- a
future refactor of after_request could drop the `view_args` check and the
leak would come back invisible to the suite.

killkrill_manager.log() is itself a no-op unless `.enabled` and `.client`
are both set (see app/killkrill.py) -- ordinary requests through the test
client never drive the ASGI lifespan that flips `.enabled` (see conftest's
`_reset_killkrill_manager`), so every test here sets both explicitly and
inspects `._log_queue` directly. That autouse fixture clears both again on
teardown regardless of what a test sets mid-body, so no manual cleanup is
needed here.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest


def _set_killkrill_capturing() -> None:
    """Enable killkrill_manager and give it a mock client so .log() queues."""
    from app.killkrill import killkrill_manager

    killkrill_manager.enabled = True
    killkrill_manager.client = MagicMock()


def _last_log_entry() -> dict[str, Any]:
    """The most recent queued log entry (the one after_request just wrote)."""
    from app.killkrill import killkrill_manager

    assert killkrill_manager._log_queue, "after_request did not log anything"
    return killkrill_manager._log_queue[-1]


class TestInvitationAcceptTokenIsMasked:
    """POST /api/v1/teams/invitations/<token>/accept."""

    @pytest.mark.asyncio
    async def test_token_does_not_reach_the_log(self, client: Any) -> None:
        """The raw token must not appear anywhere in the logged entry."""
        _set_killkrill_capturing()
        token = "regression-test-token-do-not-leak-abc123XYZ"  # noqa: S105

        response = await client.post(f"/api/v1/teams/invitations/{token}/accept")
        # Unauthenticated (no auth_headers needed -- routing populates
        # view_args, and thus what after_request logs, before auth_required
        # ever runs), so this 401s. The log assertion is independent of
        # that status code.
        assert response.status_code == 401

        entry = _last_log_entry()
        assert token not in entry["message"]
        assert token not in entry["url"]["path"]
        assert token not in str(entry)
        assert "***" in entry["url"]["path"]

    @pytest.mark.asyncio
    async def test_a_token_shaped_like_other_path_words_is_still_fully_masked(
        self, client: Any
    ) -> None:
        """A token that collides with surrounding path text still can't leak.

        Real tokens (secrets.token_urlsafe(32)) never collide with route
        literals, but this proves the mask isn't defeated by a pathological
        one: "accept" here is deliberately also a literal segment of the
        same route, and the value repeats -- .replace() must remove every
        occurrence, not just the first.
        """
        _set_killkrill_capturing()
        token = "accept-accept-accept"  # noqa: S105

        response = await client.post(f"/api/v1/teams/invitations/{token}/accept")
        assert response.status_code == 401

        entry = _last_log_entry()
        assert token not in entry["url"]["path"]
        assert token not in str(entry)
        # The route's own literal "accept" segment (not part of the token
        # parameter) must still be present -- masking the token must not
        # blank the whole path.
        assert entry["url"]["path"].endswith("/accept")
        assert entry["url"]["path"].startswith("/api/v1/teams/invitations/")


class TestConfirmEmailTokenIsMasked:
    """POST /api/v1/auth/confirm-email/<token> -- the other token-in-path route."""

    @pytest.mark.asyncio
    async def test_token_does_not_reach_the_log(self, client: Any) -> None:
        """confirm_email_endpoint has no auth_required -- it 200/401s either way."""
        _set_killkrill_capturing()
        token = "email-confirm-regression-token-9f8e7d"  # noqa: S105

        response = await client.post(f"/api/v1/auth/confirm-email/{token}")
        assert response.status_code in (200, 401)

        entry = _last_log_entry()
        assert token not in entry["message"]
        assert token not in entry["url"]["path"]
        assert token not in str(entry)
        assert "***" in entry["url"]["path"]


class TestRoutesWithoutATokenParamAreUnaffected:
    """The view_args guard must not blank paths that have nothing to hide."""

    @pytest.mark.asyncio
    async def test_a_tokenless_route_logs_its_real_path(self, client: Any) -> None:
        """/healthz carries no path params at all -- must log verbatim."""
        _set_killkrill_capturing()

        response = await client.get("/healthz")
        assert response.status_code == 200

        entry = _last_log_entry()
        assert entry["url"]["path"] == "/healthz"
        assert "***" not in entry["url"]["path"]

    @pytest.mark.asyncio
    async def test_a_route_with_a_non_token_path_param_logs_its_real_path(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """A route whose path param is named something other than "token" (e.g.

        team_id) must not be masked -- only a param literally named "token"
        is a credential here.
        """
        _set_killkrill_capturing()

        response = await client.get("/api/v1/teams/999999", headers=auth_headers)
        assert response.status_code == 404

        entry = _last_log_entry()
        assert entry["url"]["path"] == "/api/v1/teams/999999"
        assert "***" not in entry["url"]["path"]
