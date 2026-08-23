"""Functional coverage for /api/v1/mfa/* (app/mfa.py).

Before this file, MFA had zero behavioural tests -- only a route-registration
guard (test_credential_routes_are_rate_limited.py) confirmed the endpoints
were wired to the rate limiter. Every branch below is exercised with a real
TOTP code (via ``pyotp.TOTP(secret).now()``) generated against the actual
secret the setup endpoint returned, so a broken ``totp.verify(...)`` call
would fail these tests, not just execute a line.

Each test uses a fresh ``auth_headers`` user (per-test unique email from
conftest), so the account-scoped rate-limit windows (5/300s on verify,
disable, and backup-regenerate) are never shared across tests -- see
conftest's ``_clear_ratelimit_state`` autouse fixture, which additionally
resets state between tests.
"""

from __future__ import annotations

from typing import Any

import pyotp
import pytest
from app.mfa import format_backup_codes, generate_backup_codes, parse_backup_codes


async def _setup_mfa(client: Any, headers: dict[str, str]) -> dict[str, Any]:
    """POST /mfa/setup and return the parsed response body."""
    response = await client.post("/api/v1/mfa/setup", headers=headers)
    assert response.status_code == 200, f"setup failed: {await response.get_json()}"
    body: dict[str, Any] = await response.get_json()
    return body


async def _setup_and_enable_mfa(client: Any, headers: dict[str, str]) -> dict[str, Any]:
    """Run setup then verify with a genuine TOTP code; return the setup body."""
    setup_body = await _setup_mfa(client, headers)
    code = pyotp.TOTP(setup_body["secret"]).now()
    response = await client.post("/api/v1/mfa/verify", headers=headers, json={"code": code})
    assert response.status_code == 200, f"verify failed: {await response.get_json()}"
    return setup_body


class TestSetupMfa:
    """POST /api/v1/mfa/setup."""

    @pytest.mark.asyncio
    async def test_setup_returns_secret_uri_and_backup_codes(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """A fresh setup call returns a usable secret and 10 backup codes."""
        body = await _setup_mfa(client, auth_headers)
        assert len(body["secret"]) >= 16
        assert body["provisioning_uri"].startswith("otpauth://totp/")
        assert len(body["backup_codes"]) == 10
        # Generated via secrets.token_hex(4).upper() -- 8 hex chars.
        assert all(len(c) == 8 for c in body["backup_codes"])

    @pytest.mark.asyncio
    async def test_setup_again_after_enabled_is_conflict(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Once MFA is enabled, calling setup again is refused, not re-issued."""
        await _setup_and_enable_mfa(client, auth_headers)

        response = await client.post("/api/v1/mfa/setup", headers=auth_headers)
        assert response.status_code == 409
        body = await response.get_json()
        assert body["error"] == "MFA already enabled for this user"


class TestVerifyMfa:
    """POST /api/v1/mfa/verify."""

    @pytest.mark.asyncio
    async def test_missing_body_is_rejected(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """No JSON body at all -> 400, distinct from a bad code."""
        response = await client.post("/api/v1/mfa/verify", headers=auth_headers)
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Request body required"

    @pytest.mark.asyncio
    async def test_short_code_is_rejected_before_any_lookup(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """A code that isn't 6 digits 400s without ever touching the DB.

        No setup call precedes this -- if the length check didn't run first,
        this would 404 on "MFA secret not found" instead.
        """
        response = await client.post(
            "/api/v1/mfa/verify", headers=auth_headers, json={"code": "123"}
        )
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "TOTP code must be 6 digits"

    @pytest.mark.asyncio
    async def test_no_setup_secret_is_not_found(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """A well-formed 6-digit code with no prior setup -> 404, not 401."""
        response = await client.post(
            "/api/v1/mfa/verify", headers=auth_headers, json={"code": "123456"}
        )
        assert response.status_code == 404
        assert (await response.get_json())["error"] == "MFA secret not found"

    @pytest.mark.asyncio
    async def test_wrong_code_after_setup_is_unauthorized(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """A syntactically valid but wrong TOTP code is rejected, not accepted."""
        setup_body = await _setup_mfa(client, auth_headers)
        real_code = pyotp.TOTP(setup_body["secret"]).now()
        # Flip one digit so the guess is never coincidentally correct.
        wrong_digit = "1" if real_code[0] != "1" else "2"
        wrong_code = wrong_digit + real_code[1:]

        response = await client.post(
            "/api/v1/mfa/verify", headers=auth_headers, json={"code": wrong_code}
        )
        assert response.status_code == 401
        assert (await response.get_json())["error"] == "Invalid TOTP code"

    @pytest.mark.asyncio
    async def test_correct_code_enables_mfa_and_returns_backup_codes(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """The genuine happy path: real TOTP verification actually enables MFA."""
        setup_body = await _setup_mfa(client, auth_headers)
        code = pyotp.TOTP(setup_body["secret"]).now()

        response = await client.post(
            "/api/v1/mfa/verify", headers=auth_headers, json={"code": code}
        )
        assert response.status_code == 200
        body = await response.get_json()
        assert body["message"] == "MFA enabled successfully"
        assert sorted(body["backup_codes"]) == sorted(setup_body["backup_codes"])

        # Proven via the OTHER endpoint's behaviour, not by re-reading state:
        # backup-codes only 200s once MFA is genuinely enabled_at.
        follow_up = await client.get("/api/v1/mfa/backup-codes", headers=auth_headers)
        assert follow_up.status_code == 200


class TestDisableMfa:
    """POST /api/v1/mfa/disable."""

    @pytest.mark.asyncio
    async def test_missing_body_is_rejected(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """No JSON body -> 400."""
        response = await client.post("/api/v1/mfa/disable", headers=auth_headers)
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Request body required"

    @pytest.mark.asyncio
    async def test_missing_password_or_code_is_rejected(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """A body present but missing either field 400s before any DB call."""
        response = await client.post(
            "/api/v1/mfa/disable", headers=auth_headers, json={"password": "testpass123"}
        )
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Password and TOTP code required"

    @pytest.mark.asyncio
    async def test_wrong_password_is_rejected_before_totp_is_checked(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """A wrong password 401s even with a syntactically-valid TOTP code.

        auth_headers registers with password "testpass123" (conftest).
        """
        await _setup_and_enable_mfa(client, auth_headers)

        response = await client.post(
            "/api/v1/mfa/disable",
            headers=auth_headers,
            json={"password": "wrong-password", "code": "123456"},
        )
        assert response.status_code == 401
        assert (await response.get_json())["error"] == "Invalid password"

    @pytest.mark.asyncio
    async def test_correct_password_without_mfa_enabled_is_not_found(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Right password, but MFA was never set up -> 404, distinct from 401."""
        response = await client.post(
            "/api/v1/mfa/disable",
            headers=auth_headers,
            json={"password": "testpass123", "code": "123456"},
        )
        assert response.status_code == 404
        assert (await response.get_json())["error"] == "MFA not enabled"

    @pytest.mark.asyncio
    async def test_correct_password_wrong_totp_is_unauthorized(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Password verifies, but the TOTP code is wrong -> 401, MFA stays on."""
        setup_body = await _setup_and_enable_mfa(client, auth_headers)
        real_code = pyotp.TOTP(setup_body["secret"]).now()
        wrong_digit = "1" if real_code[0] != "1" else "2"
        wrong_code = wrong_digit + real_code[1:]

        response = await client.post(
            "/api/v1/mfa/disable",
            headers=auth_headers,
            json={"password": "testpass123", "code": wrong_code},
        )
        assert response.status_code == 401
        assert (await response.get_json())["error"] == "Invalid TOTP code"

        # MFA is still enabled -- the wrong code must not have disabled it.
        follow_up = await client.get("/api/v1/mfa/backup-codes", headers=auth_headers)
        assert follow_up.status_code == 200

    @pytest.mark.asyncio
    async def test_correct_password_and_totp_disables_mfa(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """The genuine happy path actually removes the MFA secret row."""
        setup_body = await _setup_and_enable_mfa(client, auth_headers)
        code = pyotp.TOTP(setup_body["secret"]).now()

        response = await client.post(
            "/api/v1/mfa/disable",
            headers=auth_headers,
            json={"password": "testpass123", "code": code},
        )
        assert response.status_code == 200
        assert (await response.get_json())["message"] == "MFA disabled successfully"

        # Proven, not assumed: backup-codes now 404s exactly like it did
        # before setup ever ran, because the row is genuinely gone.
        follow_up = await client.get("/api/v1/mfa/backup-codes", headers=auth_headers)
        assert follow_up.status_code == 404

    @pytest.mark.asyncio
    async def test_user_row_missing_mid_request_is_not_found(
        self, client: Any, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """disable_mfa_endpoint's own get_user_by_id re-fetch, forced to miss.

        auth_required (app/middleware.py) already requires this same user
        row to exist on every request via its OWN ``from .models import
        get_user_by_id`` bound at module-import time, so this branch is
        only reachable if the row disappears in the narrow window between
        that check and disable_mfa_endpoint's own re-fetch -- a real race,
        not something a normal request can trigger.

        Exercised directly by patching ``app.models.get_user_by_id``:
        mfa.py's ``from .models import get_user_by_id`` runs INSIDE the
        function body, so it re-resolves the (now patched) attribute on
        every call, while middleware.py's own copy -- imported at module
        load time, before this patch ever applies -- is untouched and still
        lets the request through.
        """
        from app import models

        async def _always_miss(user_id: int) -> dict[str, Any] | None:
            return None

        monkeypatch.setattr(models, "get_user_by_id", _always_miss)

        response = await client.post(
            "/api/v1/mfa/disable",
            headers=auth_headers,
            json={"password": "testpass123", "code": "123456"},
        )
        assert response.status_code == 404
        assert (await response.get_json())["error"] == "User not found"


class TestBackupCodes:
    """GET /api/v1/mfa/backup-codes."""

    @pytest.mark.asyncio
    async def test_not_enabled_is_not_found(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """No MFA setup at all -> 404."""
        response = await client.get("/api/v1/mfa/backup-codes", headers=auth_headers)
        assert response.status_code == 404
        assert (await response.get_json())["error"] == "MFA not enabled"

    @pytest.mark.asyncio
    async def test_setup_without_verify_is_still_not_enabled(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """A row exists after setup, but enabled_at is still NULL -> 404.

        Distinguishes "no row" from "row present but not yet verified" --
        both must read as not-enabled to the caller.
        """
        await _setup_mfa(client, auth_headers)

        response = await client.get("/api/v1/mfa/backup-codes", headers=auth_headers)
        assert response.status_code == 404
        assert (await response.get_json())["error"] == "MFA not enabled"

    @pytest.mark.asyncio
    async def test_enabled_returns_the_original_codes(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Once verified, the exact codes issued at setup are returned."""
        setup_body = await _setup_and_enable_mfa(client, auth_headers)

        response = await client.get("/api/v1/mfa/backup-codes", headers=auth_headers)
        assert response.status_code == 200
        body = await response.get_json()
        assert sorted(body["backup_codes"]) == sorted(setup_body["backup_codes"])


class TestRegenerateBackupCodes:
    """POST /api/v1/mfa/backup-codes/regenerate."""

    @pytest.mark.asyncio
    async def test_missing_body_is_rejected(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """No JSON body -> 400."""
        response = await client.post("/api/v1/mfa/backup-codes/regenerate", headers=auth_headers)
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Request body required"

    @pytest.mark.asyncio
    async def test_missing_code_is_rejected(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """A body with no code field 400s distinctly from a wrong code."""
        response = await client.post(
            "/api/v1/mfa/backup-codes/regenerate", headers=auth_headers, json={"code": ""}
        )
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "TOTP code required"

    @pytest.mark.asyncio
    async def test_not_enabled_is_not_found(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """No MFA setup at all -> 404, checked after the code-presence check."""
        response = await client.post(
            "/api/v1/mfa/backup-codes/regenerate", headers=auth_headers, json={"code": "123456"}
        )
        assert response.status_code == 404
        assert (await response.get_json())["error"] == "MFA not enabled"

    @pytest.mark.asyncio
    async def test_wrong_code_is_unauthorized(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """A syntactically valid but wrong TOTP code is rejected."""
        setup_body = await _setup_and_enable_mfa(client, auth_headers)
        real_code = pyotp.TOTP(setup_body["secret"]).now()
        wrong_digit = "1" if real_code[0] != "1" else "2"
        wrong_code = wrong_digit + real_code[1:]

        response = await client.post(
            "/api/v1/mfa/backup-codes/regenerate",
            headers=auth_headers,
            json={"code": wrong_code},
        )
        assert response.status_code == 401
        assert (await response.get_json())["error"] == "Invalid TOTP code"

    @pytest.mark.asyncio
    async def test_correct_code_replaces_the_codes(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Regeneration actually persists a new set, not just returns one."""
        setup_body = await _setup_and_enable_mfa(client, auth_headers)
        code = pyotp.TOTP(setup_body["secret"]).now()

        response = await client.post(
            "/api/v1/mfa/backup-codes/regenerate", headers=auth_headers, json={"code": code}
        )
        assert response.status_code == 200
        body = await response.get_json()
        assert body["message"] == "Backup codes regenerated"
        new_codes = body["backup_codes"]
        assert len(new_codes) == 10
        assert sorted(new_codes) != sorted(setup_body["backup_codes"])

        # Persisted, not just returned: a fresh GET sees the same new set.
        follow_up = await client.get("/api/v1/mfa/backup-codes", headers=auth_headers)
        assert sorted((await follow_up.get_json())["backup_codes"]) == sorted(new_codes)


class TestParseBackupCodes:
    """Unit coverage for the small pure helpers, not reachable via HTTP alone."""

    def test_empty_string_returns_empty_list(self) -> None:
        """An empty stored value parses to an empty list, not an error."""
        assert parse_backup_codes("") == []

    def test_malformed_json_returns_empty_list(self) -> None:
        """Corrupt JSON degrades to an empty list rather than raising."""
        assert parse_backup_codes("{not valid json") == []

    def test_valid_json_non_list_returns_empty_list(self) -> None:
        """Well-formed JSON that isn't a list (e.g. an object) is rejected."""
        assert parse_backup_codes('{"a": 1}') == []

    def test_round_trips_through_format(self) -> None:
        """format_backup_codes -> parse_backup_codes recovers the same list."""
        codes = generate_backup_codes()
        assert parse_backup_codes(format_backup_codes(codes)) == codes


class TestLoginWithMfaEnabled:
    """POST /api/v1/auth/login's MFA branch (app/auth.py).

    Previously untested end-to-end: an account with MFA enabled must
    supply a valid TOTP code to log in at all.
    """

    @pytest.mark.asyncio
    async def test_missing_code_is_rejected_with_mfa_required_flag(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """No mfa_code at all -> 401, with mfa_required=True.

        So the client knows to prompt for a code rather than treat this
        as a bad password.
        """
        setup_body = await _setup_and_enable_mfa(client, auth_headers)
        assert setup_body  # MFA is now enabled for this account

        profile = await client.get("/api/v1/users/me", headers=auth_headers)
        email = (await profile.get_json())["email"]

        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "testpass123"}
        )
        assert response.status_code == 401
        body = await response.get_json()
        assert body["mfa_required"] is True

    @pytest.mark.asyncio
    async def test_wrong_code_is_rejected(self, client: Any, auth_headers: dict[str, str]) -> None:
        """A syntactically valid but wrong TOTP code fails login."""
        setup_body = await _setup_and_enable_mfa(client, auth_headers)
        real_code = pyotp.TOTP(setup_body["secret"]).now()
        wrong_digit = "1" if real_code[0] != "1" else "2"
        wrong_code = wrong_digit + real_code[1:]

        profile = await client.get("/api/v1/users/me", headers=auth_headers)
        email = (await profile.get_json())["email"]

        response = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "testpass123", "mfa_code": wrong_code},
        )
        assert response.status_code == 401
        assert (await response.get_json())["error"] == "Invalid MFA code"

    @pytest.mark.asyncio
    async def test_correct_code_logs_in_successfully(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """The genuine happy path: password + real TOTP code together succeed."""
        setup_body = await _setup_and_enable_mfa(client, auth_headers)
        code = pyotp.TOTP(setup_body["secret"]).now()

        profile = await client.get("/api/v1/users/me", headers=auth_headers)
        email = (await profile.get_json())["email"]

        response = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "testpass123", "mfa_code": code},
        )
        assert response.status_code == 200
        assert "access_token" in (await response.get_json())
