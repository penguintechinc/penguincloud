"""``--dev`` mode: the condition matrix, the cap, and what it must NOT touch.

general.md specifies this flag precisely, and two of its requirements are
the ones that make it a licensing control rather than a backdoor:

* **Re-evaluate continuously, never latch at boot.** "If the user count
  rises above 1 by any path, premium features must deactivate. A boolean
  latched at boot is a licensing hole." :class:`TestNoBootTimeLatch` is that
  requirement.
* **Enforce the user count server-side, from the identity table** — never
  from a client claim, header or cached count.

And one that makes it safe: it unlocks *features*, nothing else. Auth,
authz and tenant isolation are unchanged, asserted in
:class:`TestDevModeUnlocksFeaturesOnly` — a "dev mode" that also relaxed a
scope check would be a far worse bug than the licensing one it exists to
bound.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest
from app import devmode, licensing, quotas
from quart import Quart


@pytest.fixture(autouse=True)
def _clean_devmode_state() -> Any:
    """Every test starts with the flag unset and the notice unprinted."""
    devmode.reset()
    yield
    devmode.reset()


def _activate(monkeypatch: pytest.MonkeyPatch, users: int = 0) -> None:
    """Put all three conditions in the TRUE position."""
    monkeypatch.setattr(devmode, "_requested", True)
    monkeypatch.setattr(devmode, "domain_permits", lambda: True)

    async def _count() -> int:
        return users

    monkeypatch.setattr(devmode, "user_count", _count)


class TestArgvRecording:
    """The flag records an input; it never records a decision."""

    def test_flag_is_recognised(self) -> None:
        """Flag is recognised."""
        assert devmode.request_from_argv(["--dev"]) is True
        assert devmode.is_requested() is True

    def test_absent_flag_is_not_requested(self) -> None:
        """Absent flag is not requested."""
        assert devmode.request_from_argv(["--verbose", "8000"]) is False
        assert devmode.is_requested() is False

    def test_requested_is_not_active(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Passing the flag alone unlocks nothing.

        The distinction the whole design rests on: ``is_requested`` is what
        the operator asked for, ``is_active`` is what the conditions allow.
        """
        devmode.request_from_argv(["--dev"])
        monkeypatch.setattr(devmode, "domain_permits", lambda: False)
        assert devmode.is_requested() is True


class TestConditionMatrix:
    """Each condition false makes it inert. All true makes it active."""

    @pytest.mark.asyncio
    async def test_all_conditions_true_activates(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The positive case, so nothing below passes for the wrong reason.

        A matrix of "inert" assertions is satisfied by a function that
        returns False unconditionally; this is what makes the rest mean
        something.
        """
        _activate(monkeypatch, users=1)
        assert await devmode.is_active() is True

    @pytest.mark.asyncio
    async def test_inert_when_flag_not_passed(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Inert when flag not passed."""
        _activate(monkeypatch, users=0)
        monkeypatch.setattr(devmode, "_requested", False)
        assert await devmode.is_active() is False

    @pytest.mark.asyncio
    async def test_inert_on_a_non_penguintech_domain(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Inert on a non penguintech domain."""
        _activate(monkeypatch, users=0)
        monkeypatch.setattr(devmode, "domain_permits", lambda: False)
        assert await devmode.is_active() is False

    @pytest.mark.asyncio
    async def test_inert_when_more_than_one_user_exists(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Inert when more than one user exists."""
        _activate(monkeypatch, users=2)
        assert await devmode.is_active() is False

    @pytest.mark.asyncio
    async def test_an_unreadable_identity_table_is_inert(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A count that cannot be read must fail closed, not 500.

        ``user_count`` answers a number that FAILS the cap rather than
        raising, so a database problem makes dev mode inert instead of
        taking the portal down with it — and never accidentally unlocks.
        """
        monkeypatch.setattr(devmode, "_requested", True)
        monkeypatch.setattr(devmode, "domain_permits", lambda: True)

        def _explode() -> Any:
            raise RuntimeError("identity table unavailable")

        monkeypatch.setattr(devmode, "get_db", _explode)

        assert await devmode.user_count() > devmode.MAX_DEV_MODE_USERS
        assert await devmode.is_active() is False


class TestDomainCondition:
    """PenguinTech-controlled domains only, on the shared matcher."""

    @pytest.mark.parametrize(
        "host,permitted",
        [
            ("portal.penguincloud.io", True),
            ("penguincloud.localhost.local", True),
            ("penguincloud.penguintech.cloud", True),
            ("customer.example.com", False),
            ("evilpenguincloud.io", False),
            ("", False),
        ],
    )
    def test_domain_permits(
        self, host: str, permitted: bool, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Domain permits."""
        monkeypatch.setattr(devmode, "resolved_host", lambda: host)
        assert devmode.domain_permits() is permitted

    def test_host_comes_from_configuration(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The configured domain is the domain, request or no request."""
        monkeypatch.setenv("BASE_URL", "penguincloud.localhost.local")
        assert devmode.resolved_host() == "penguincloud.localhost.local"

    @pytest.mark.asyncio
    async def test_a_spoofed_host_header_does_not_permit_dev_mode(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A caller cannot name the domain dev mode is evaluated against.

        The header used to win over configuration. Anyone able to reach the
        pod — which, on a self-hosted deployment, is the operator the
        single-user cap exists to constrain — could therefore satisfy the
        domain condition by asserting it about themselves.
        """
        monkeypatch.setenv("BASE_URL", "https://portal.customer.example.com")
        monkeypatch.delenv("SERVER_NAME", raising=False)
        async with app.test_request_context(
            "/api/v1/features", headers={"Host": "portal.penguincloud.io"}
        ):
            assert devmode.resolved_host() == "portal.customer.example.com"
            assert devmode.domain_permits() is False

    @pytest.mark.parametrize(
        "host,permitted",
        [
            # A product .app domain: PenguinTech-controlled per
            # penguintech.md and named by general.md's dev-mode condition,
            # but NOT in penguin-licensing's licence-bypass list. This is
            # the divergence that makes --dev observable on its own.
            ("portal.waddles.app", True),
            ("gough.app", True),
            ("evilgough.app", False),
            ("gough.app.example.com", False),
        ],
    )
    def test_product_app_domains_permit_dev_mode_but_not_the_bypass(
        self, host: str, permitted: bool, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Product app domains permit dev mode but not the bypass."""
        monkeypatch.setattr(devmode, "resolved_host", lambda: host)
        assert devmode.domain_permits() is permitted
        # The licence bypass is deliberately NOT widened to match.
        assert licensing.host_is_license_exempt(host) is False


class TestNoBootTimeLatch:
    """The requirement general.md calls out by name."""

    @pytest.mark.asyncio
    async def test_growing_past_one_user_deactivates_immediately(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Active, then a second user appears, then inert — no restart.

        This is the licensing hole a boolean cached at startup creates: an
        operator brings the deployment up with one user, premium unlocks,
        they add a team, and a latched flag keeps the entire paid feature
        set on for an organisation that never bought it.
        """
        counts = [1, 1, 2, 5]

        async def _count() -> int:
            return counts.pop(0)

        monkeypatch.setattr(devmode, "_requested", True)
        monkeypatch.setattr(devmode, "domain_permits", lambda: True)
        monkeypatch.setattr(devmode, "user_count", _count)

        assert await devmode.is_active() is True
        assert await devmode.is_active() is True
        assert await devmode.is_active() is False
        assert await devmode.is_active() is False

    @pytest.mark.asyncio
    async def test_the_notice_latch_does_not_latch_activation(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One-shot printing must not become one-shot deciding.

        ``_notice_emitted`` exists so the stderr box is not reprinted per
        request. If it were ever consulted by ``is_active``, the first
        activation would pin the answer forever — exactly the latch this
        design forbids.
        """
        _activate(monkeypatch, users=0)
        assert await devmode.is_active() is True
        assert devmode._notice_emitted is True

        monkeypatch.setattr(devmode, "domain_permits", lambda: False)
        assert await devmode.is_active() is False


class TestOperatorNotice:
    """Verbatim, on stderr, never suppressible."""

    def test_notice_is_the_general_md_text(self) -> None:
        """Notice is the general md text."""
        for line in (
            "DEVELOPMENT MODE (--dev) — ALL PREMIUM FEATURES UNLOCKED",
            "For testing and evaluation only, limited to a single user.",
            "Use of this mode to obtain licensed functionality without a valid",
            "commercial license is a breach of the PenguinTech commercial",
            "license terms. See LICENSE.md.",
        ):
            assert line in devmode.DEV_MODE_NOTICE
        assert devmode.DEV_MODE_NOTICE.startswith("╭")
        assert devmode.DEV_MODE_NOTICE.endswith("╯")

    @pytest.mark.asyncio
    async def test_activation_prints_to_stderr_not_stdout(
        self,
        app: Quart,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Stdout is piped and parsed; a licensing warning there is lost."""
        _activate(monkeypatch, users=0)

        assert await devmode.is_active() is True

        captured = capsys.readouterr()
        assert devmode.DEV_MODE_NOTICE in captured.err
        assert devmode.DEV_MODE_NOTICE not in captured.out

    @pytest.mark.asyncio
    async def test_the_notice_is_printed_once_not_per_request(
        self,
        app: Quart,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The notice is printed once not per request."""
        _activate(monkeypatch, users=0)

        for _ in range(4):
            await devmode.is_active()

        assert capsys.readouterr().err.count("DEVELOPMENT MODE") == 1

    @pytest.mark.asyncio
    async def test_the_warn_log_carries_the_observed_user_count(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """general.md: log "the resolved domain and user count".

        It logged ``max_users`` — the constant 1 — which is not a fact about
        the deployment. An auditor reading captured logs could not tell an
        activation on an empty deployment from one at the cap.
        """
        recorded: list[dict[str, Any]] = []

        class _Recorder:
            def warning(self, event: str, **fields: Any) -> None:
                recorded.append({"event": event, **fields})

        monkeypatch.setattr(devmode, "log", _Recorder())
        _activate(monkeypatch, users=1)

        assert await devmode.is_active() is True

        activation = [line for line in recorded if line["event"] == "dev_mode_active"]
        assert activation, recorded
        assert activation[0]["user_count"] == 1
        assert activation[0]["domain"] == devmode.resolved_host()

    def test_startup_announcement_requires_the_flag(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Startup announcement requires the flag."""
        devmode.request_from_argv([])
        devmode.announce_at_startup()
        assert "DEVELOPMENT MODE" not in capsys.readouterr().err

        devmode.request_from_argv(["--dev"])
        devmode.announce_at_startup()
        assert "DEVELOPMENT MODE" in capsys.readouterr().err


class TestUserCap:
    """The second user is refused, at every path that can create one."""

    @pytest.mark.asyncio
    async def test_first_user_is_permitted(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The cap is one user, not zero — a fresh deployment must work."""
        _activate(monkeypatch, users=0)
        assert await devmode.user_creation_refusal() is None
        await devmode.assert_user_creation_allowed()

    @pytest.mark.asyncio
    async def test_second_user_is_refused_with_a_reason(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Second user is refused with a reason."""
        _activate(monkeypatch, users=1)
        refusal = await devmode.user_creation_refusal()

        assert refusal is not None
        body, status = refusal
        # Same status and same key set as every other scale wall, so one
        # upgrade UI and one log reader handle all of them; `error` is what
        # names the specific cause. See quotas.scale_refusal_body.
        assert status == quotas.SCALE_REFUSAL_STATUS == 402
        assert body["error"] == "dev_mode_user_cap"
        assert body["dimension"] == "users"
        assert body["limit"] == devmode.MAX_DEV_MODE_USERS
        assert body["current"] == 1
        assert body["required_tier"] is None
        assert "--dev" in body["message"]
        assert set(body) == set(
            quotas.scale_refusal_body(
                error="quota_exceeded",
                message="",
                dimension="teams",
                limit=1,
                current=1,
                current_tier="community",
                required_tier=None,
            )
        )

    @pytest.mark.asyncio
    async def test_the_model_layer_backstop_raises(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A cap enforced at only some call sites is not a cap.

        The routes answer a clean 403 first; this is what a future route,
        seed script or background job hits if it inserts a user without
        asking.
        """
        _activate(monkeypatch, users=1)
        with pytest.raises(devmode.DevModeUserCapExceededError):
            await devmode.assert_user_creation_allowed()

    @pytest.mark.asyncio
    async def test_no_cap_when_dev_mode_is_inert(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A normal deployment is not silently limited to one user."""
        _activate(monkeypatch, users=50)
        monkeypatch.setattr(devmode, "_requested", False)

        assert await devmode.user_creation_refusal() is None
        await devmode.assert_user_creation_allowed()

    @pytest.mark.asyncio
    async def test_registration_route_refuses_the_second_user(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End to end through POST /api/v1/auth/register."""
        _activate(monkeypatch, users=1)

        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "second-user@example.com",
                "password": "a-sufficiently-long-password",
                "full_name": "Second User",
            },
        )

        assert response.status_code == 402
        assert (await response.get_json())["error"] == "dev_mode_user_cap"

    @pytest.mark.asyncio
    async def test_admin_create_route_refuses_the_second_user(
        self,
        client: Any,
        admin_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An admin creating users by hand is bound by the same cap."""
        _activate(monkeypatch, users=1)

        response = await client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "email": "admin-made@example.com",
                "password": "a-sufficiently-long-password",
                "full_name": "Admin Made",
                "role": "viewer",
            },
        )

        assert response.status_code == 402
        assert (await response.get_json())["error"] == "dev_mode_user_cap"

    @pytest.mark.asyncio
    async def test_registration_still_works_without_dev_mode(self, client: Any) -> None:
        """The cap must not leak into a normal deployment."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "normal-signup@example.com",
                "password": "a-sufficiently-long-password",
                "full_name": "Normal Signup",
            },
        )

        assert response.status_code != 403


class TestDevModeUnlocksFeaturesOnly:
    """It never touches authentication, authorization or tenant isolation."""

    @pytest.mark.asyncio
    async def test_unauthenticated_calls_are_still_rejected(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unauthenticated calls are still rejected."""
        _activate(monkeypatch, users=0)

        response = await client.get("/api/v1/features")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_scope_gates_still_deny(
        self, client: Any, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A viewer stays a viewer.

        ``license:read`` is carried by the platform-admin bundle and no
        other. If dev mode ever relaxed a scope check, this is where it
        would show — and that would be a far worse defect than the
        licensing one dev mode exists to bound.
        """
        _activate(monkeypatch, users=0)

        response = await client.get("/api/v1/license/status", headers=auth_headers)
        assert response.status_code == 403


class TestFlagIsUndocumented:
    """Not a security control, but asserted so it stays true."""

    def test_dev_flag_is_absent_from_the_openapi_document(self) -> None:
        """Dev flag is absent from the openapi document."""
        from pathlib import Path

        spec = (Path(__file__).resolve().parents[2] / "openapi" / "v1.yaml").read_text(
            encoding="utf-8"
        )

        assert "--dev" not in spec

    def test_the_entrypoint_publishes_no_help_surface(self) -> None:
        """There is no ``--help`` for the flag to appear in.

        Asserted as "no argparse at all" rather than "the string --dev is
        absent from the file": the source necessarily names the flag it
        implements, and a check that forbade that would only be satisfiable
        by deleting the comments explaining it. If an argument parser is
        ever added here, ``--dev`` must be registered with
        ``help=argparse.SUPPRESS`` and this assertion replaced with one
        that checks the rendered help text.
        """
        from pathlib import Path

        run_py = (
            Path(__file__).resolve().parents[2] / "services" / "portal-api" / "run.py"
        ).read_text(encoding="utf-8")

        assert "argparse" not in run_py
        assert "add_argument" not in run_py


class TestArgvSourceIsTheProcess:
    """``request_from_argv()`` with no argument reads the real argv."""

    def test_defaults_to_sys_argv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Defaults to sys argv."""
        monkeypatch.setattr(sys, "argv", ["run.py", "--dev"])
        assert devmode.request_from_argv() is True

        monkeypatch.setattr(sys, "argv", ["run.py"])
        assert devmode.request_from_argv() is False
