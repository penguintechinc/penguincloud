"""F1: self-service registration must be CLOSED unless explicitly opened.

The bug, precisely
===================
``POST /api/v1/auth/register`` accepted anyone, on every install, with no
env var, flag or config to disable it. The only lever was client-side
(``showSignUp={false}`` in the webui's Login.tsx) -- exactly the
UI-gate-is-not-a-server-gate pattern this codebase already fixed once for
product modules (see app/flags.py's ``product_gate_refusal`` docstring).
Consequences on every install: anonymous account creation minted a valid
access token, and each signup consumed a licensed team slot
(app.auth.register's ``quotas.quota_refusal("teams", ...)`` call).

The fix
=======
``Config.ALLOW_SELF_REGISTRATION`` -- closed (``False``) unless the
operator explicitly sets ``ALLOW_SELF_REGISTRATION=true``. Enforced
server-side, as the FIRST thing ``register()`` does -- before parsing the
request body, so a closed deployment never touches an anonymous caller's
payload at all.
"""

from __future__ import annotations

import importlib
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from app import config as config_module
from quart import Quart


@contextmanager
def _env_var(name: str, value: str | None) -> Iterator[None]:
    """Set (or delete) an env var for the block, reloading app.config both ways.

    Copied from test_config_env_parsing.py's own helper rather than
    imported: that module documents (see its own docstring) why every
    reload-based test restores and reloads again in a ``finally``, not
    fixture teardown, and duplicating the four lines here keeps this file
    self-contained the same way every other derived-guard/config test file
    in this suite is.
    """
    original = os.environ.get(name)
    had_original = name in os.environ
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
    importlib.reload(config_module)
    try:
        yield
    finally:
        if had_original:
            os.environ[name] = original  # type: ignore[assignment]
        else:
            os.environ.pop(name, None)
        importlib.reload(config_module)


class TestProductionDefaultIsClosed:
    """The class-body ``os.getenv`` default, exercised through a real reload.

    Same reasoning as test_config_env_parsing.py's own
    ``TestConfigClassBodyActuallyReadsTheEnvironment``: a subclass override
    never touches this line, so only a real env var + reload proves the
    DEFAULT -- what a fresh deployment configuring nothing actually gets.
    """

    def test_unset_resolves_to_closed(self) -> None:
        """The acceptance question: configure nothing, get registration OFF."""
        with _env_var("ALLOW_SELF_REGISTRATION", None):
            assert config_module.Config.ALLOW_SELF_REGISTRATION is False

    def test_explicit_false_is_closed(self) -> None:
        """An explicit `false` behaves identically to unset."""
        with _env_var("ALLOW_SELF_REGISTRATION", "false"):
            assert config_module.Config.ALLOW_SELF_REGISTRATION is False

    def test_explicit_true_opens_it(self) -> None:
        """The one, explicit, opt-IN lever -- never the reverse."""
        with _env_var("ALLOW_SELF_REGISTRATION", "true"):
            assert config_module.Config.ALLOW_SELF_REGISTRATION is True

    def test_module_is_restored_to_the_real_environment(self) -> None:
        """Sanity check mirroring test_config_env_parsing.py's own.

        If a test above leaked ALLOW_SELF_REGISTRATION=true past its own
        ``_env_var`` block, every OTHER test in this file (and
        TestingConfig-based fixtures elsewhere, which declare their OWN
        value explicitly and are therefore immune) would silently run
        against the wrong default.
        """
        assert "ALLOW_SELF_REGISTRATION" not in os.environ


async def _team_count(app: Quart) -> int:
    from app.quotas import count_teams

    async with app.app_context():
        return await count_teams()


class TestClosedDeploymentRefusesRegistration:
    """The server-side gate, driven through a real HTTP request.

    ``client``/``app`` come from conftest.py, where TestingConfig declares
    ``ALLOW_SELF_REGISTRATION = True`` explicitly (see that class's own
    docstring) so every OTHER test in this suite -- which registers
    throwaway accounts freely -- is unaffected. Flipping it back to the
    production default on the already-built app is what proves the gate,
    without needing a second app/DB stood up per test.
    """

    @pytest.mark.asyncio
    async def test_register_is_refused_with_403_and_no_user_created(
        self, client: Any, app: Quart
    ) -> None:
        """The consequence question: no row, no token, no metered team."""
        app.config["ALLOW_SELF_REGISTRATION"] = False
        email = f"closed-gate-{uuid.uuid4().hex[:8]}@example.com"
        before = await _team_count(app)

        response = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "testpass123", "full_name": "Nope"},
        )

        assert response.status_code == 403
        body = await response.get_json()
        assert body["error"] == "registration_disabled"
        assert "ALLOW_SELF_REGISTRATION" in body["message"]

        from app.models import get_user_by_email

        async with app.app_context():
            assert await get_user_by_email(email) is None

        # The consequence named in the module docstring: no side effect
        # metered against the licensed team quota either.
        assert await _team_count(app) == before

    @pytest.mark.asyncio
    async def test_refusal_runs_before_body_validation(self, client: Any, app: Quart) -> None:
        """Closed means closed even for a request that would otherwise 400.

        Proves the gate is the FIRST thing register() does: a payload
        missing every required field still gets 403, not 400 -- if this
        ever regresses to 400 the gate has been pushed past the body
        parsing it is supposed to precede.
        """
        app.config["ALLOW_SELF_REGISTRATION"] = False

        response = await client.post("/api/v1/auth/register", json={})

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_open_deployment_still_registers(self, client: Any, app: Quart) -> None:
        """The converse: explicitly opened, registration behaves as before."""
        app.config["ALLOW_SELF_REGISTRATION"] = True
        email = f"open-gate-{uuid.uuid4().hex[:8]}@example.com"

        response = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "testpass123", "full_name": "Yes"},
        )

        assert response.status_code == 201
