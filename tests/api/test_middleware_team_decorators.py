"""Unit coverage for app.middleware's team_*_required decorators.

Not currently wired to any route -- teams.py gates on
app.authz.require_team_scope instead (see that module's docstring: scope
checks, never role-name comparisons). These three decorators (and their
shared _coerce_team_id helper) are still importable, public middleware
surface and are exactly the role-name-branching pattern security.md
forbids for anything that IS wired up -- worth a direct unit-level check
that each still behaves as documented, in isolation from any route.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.middleware import (
    _coerce_team_id,
    team_admin_required,
    team_member_required,
    team_owner_required,
)
from quart import Quart, g


class TestCoerceTeamId:
    """Coerce Team Id."""

    def test_bool_is_rejected_even_though_it_is_an_int_subclass(self) -> None:
        """Bool is rejected even though it is an int subclass."""
        assert _coerce_team_id(True) is None
        assert _coerce_team_id(False) is None

    def test_int_passes_through(self) -> None:
        """Int passes through."""
        assert _coerce_team_id(7) == 7

    def test_numeric_string_is_parsed(self) -> None:
        """Numeric string is parsed."""
        assert _coerce_team_id("42") == 42

    def test_non_numeric_string_is_rejected(self) -> None:
        """Non numeric string is rejected."""
        assert _coerce_team_id("not-a-number") is None

    def test_none_is_rejected(self) -> None:
        """None is rejected."""
        assert _coerce_team_id(None) is None


async def _call_decorated(
    app: Quart,
    decorator: Any,
    *,
    user: dict[str, Any] | None,
    team_id: Any,
    role_lookup_result: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Any, int] | Any:
    """Call decorated."""

    async def _view(**kwargs: Any) -> tuple[dict[str, str], int]:
        """View."""
        return {"reached": "yes"}, 200

    async def _fake_get_role(user_id: int, tid: int) -> str | None:
        """Fake get role."""
        return role_lookup_result

    monkeypatch.setattr("app.models.get_user_team_role", _fake_get_role)

    decorated = decorator(_view)
    async with app.test_request_context("/x"):
        if user is not None:
            g.current_user = user
        return await decorated(team_id=team_id)


@pytest.mark.usefixtures("_product_flags_enabled")
class TestTeamMemberRequired:
    """Team Member Required."""

    @pytest.mark.asyncio
    async def test_no_user_is_401(self, app: Quart, monkeypatch: pytest.MonkeyPatch) -> None:
        """No user is 401."""
        result = await _call_decorated(
            app,
            team_member_required,
            user=None,
            team_id=1,
            role_lookup_result=None,
            monkeypatch=monkeypatch,
        )
        assert result == ({"error": "Authentication required"}, 401)

    @pytest.mark.asyncio
    async def test_missing_team_id_is_400(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing team id is 400."""
        result = await _call_decorated(
            app,
            team_member_required,
            user={"id": 1},
            team_id=None,
            role_lookup_result=None,
            monkeypatch=monkeypatch,
        )
        assert result == ({"error": "Team ID required"}, 400)

    @pytest.mark.asyncio
    async def test_non_member_is_403(self, app: Quart, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non member is 403."""
        result = await _call_decorated(
            app,
            team_member_required,
            user={"id": 1},
            team_id=7,
            role_lookup_result=None,
            monkeypatch=monkeypatch,
        )
        assert result == ({"error": "Not a member of this team"}, 403)

    @pytest.mark.asyncio
    async def test_any_role_including_viewer_passes(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Any role including viewer passes."""
        result = await _call_decorated(
            app,
            team_member_required,
            user={"id": 1},
            team_id=7,
            role_lookup_result="viewer",
            monkeypatch=monkeypatch,
        )
        assert result == ({"reached": "yes"}, 200)


@pytest.mark.usefixtures("_product_flags_enabled")
class TestTeamAdminRequired:
    """Team Admin Required."""

    @pytest.mark.asyncio
    async def test_no_user_is_401(self, app: Quart, monkeypatch: pytest.MonkeyPatch) -> None:
        """No user is 401."""
        result = await _call_decorated(
            app,
            team_admin_required,
            user=None,
            team_id=1,
            role_lookup_result=None,
            monkeypatch=monkeypatch,
        )
        assert result == ({"error": "Authentication required"}, 401)

    @pytest.mark.asyncio
    async def test_missing_team_id_is_400(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing team id is 400."""
        result = await _call_decorated(
            app,
            team_admin_required,
            user={"id": 1},
            team_id="not-numeric",
            role_lookup_result=None,
            monkeypatch=monkeypatch,
        )
        assert result == ({"error": "Team ID required"}, 400)

    @pytest.mark.asyncio
    async def test_plain_member_is_403(self, app: Quart, monkeypatch: pytest.MonkeyPatch) -> None:
        """Plain member is 403."""
        result = await _call_decorated(
            app,
            team_admin_required,
            user={"id": 1},
            team_id=7,
            role_lookup_result="member",
            monkeypatch=monkeypatch,
        )
        assert result == ({"error": "Team admin access required"}, 403)

    @pytest.mark.asyncio
    async def test_admin_role_passes(self, app: Quart, monkeypatch: pytest.MonkeyPatch) -> None:
        """Admin role passes."""
        result = await _call_decorated(
            app,
            team_admin_required,
            user={"id": 1},
            team_id=7,
            role_lookup_result="admin",
            monkeypatch=monkeypatch,
        )
        assert result == ({"reached": "yes"}, 200)

    @pytest.mark.asyncio
    async def test_owner_role_also_passes(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Owner role also passes."""
        result = await _call_decorated(
            app,
            team_admin_required,
            user={"id": 1},
            team_id=7,
            role_lookup_result="owner",
            monkeypatch=monkeypatch,
        )
        assert result == ({"reached": "yes"}, 200)


@pytest.mark.usefixtures("_product_flags_enabled")
class TestTeamOwnerRequired:
    """Team Owner Required."""

    @pytest.mark.asyncio
    async def test_no_user_is_401(self, app: Quart, monkeypatch: pytest.MonkeyPatch) -> None:
        """No user is 401."""
        result = await _call_decorated(
            app,
            team_owner_required,
            user=None,
            team_id=1,
            role_lookup_result=None,
            monkeypatch=monkeypatch,
        )
        assert result == ({"error": "Authentication required"}, 401)

    @pytest.mark.asyncio
    async def test_missing_team_id_is_400(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing team id is 400."""
        result = await _call_decorated(
            app,
            team_owner_required,
            user={"id": 1},
            team_id=None,
            role_lookup_result=None,
            monkeypatch=monkeypatch,
        )
        assert result == ({"error": "Team ID required"}, 400)

    @pytest.mark.asyncio
    async def test_admin_is_not_owner_and_is_403(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Admin is not owner and is 403."""
        result = await _call_decorated(
            app,
            team_owner_required,
            user={"id": 1},
            team_id=7,
            role_lookup_result="admin",
            monkeypatch=monkeypatch,
        )
        assert result == ({"error": "Team owner access required"}, 403)

    @pytest.mark.asyncio
    async def test_owner_passes(self, app: Quart, monkeypatch: pytest.MonkeyPatch) -> None:
        """Owner passes."""
        result = await _call_decorated(
            app,
            team_owner_required,
            user={"id": 1},
            team_id=7,
            role_lookup_result="owner",
            monkeypatch=monkeypatch,
        )
        assert result == ({"reached": "yes"}, 200)
