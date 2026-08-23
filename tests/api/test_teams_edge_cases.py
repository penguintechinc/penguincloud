"""Remaining branch coverage in app/teams.py.

Not reached by test_teams.py or test_team_membership_management.py. Those
two files already cover slug-format rejection (one shape), the
membership-gated CRUD/invitation pre-checks with genuine ownership, and
duplicate-slug's status code. What's left: ``validate_team_slug``'s other
internal branches (empty/too-short/too-long/leading-hyphen -- none of which
the existing "contains a space" case exercises), and
``create_team_endpoint``'s quota-refusal path, which no test in this repo
had reached.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.teams import validate_team_slug
from quart import Quart
from test_team_membership_management import _make_owned_team


class TestValidateTeamSlug:
    """Pure-function coverage for every branch validate_team_slug can take."""

    def test_empty_string_is_invalid(self) -> None:
        """An empty slug fails the falsy check, not the length check."""
        assert validate_team_slug("") is False

    def test_two_characters_is_too_short(self) -> None:
        """One below the 3-char floor is rejected."""
        assert validate_team_slug("ab") is False

    def test_three_characters_is_the_valid_floor(self) -> None:
        """Exactly 3 chars is accepted -- the floor is inclusive."""
        assert validate_team_slug("abc") is True

    def test_sixty_four_characters_is_too_long(self) -> None:
        """One above the 63-char ceiling is rejected."""
        assert validate_team_slug("a" * 64) is False

    def test_sixty_three_characters_is_the_valid_ceiling(self) -> None:
        """Exactly 63 chars is accepted -- the ceiling is inclusive."""
        assert validate_team_slug("a" * 63) is True

    def test_leading_hyphen_is_invalid(self) -> None:
        """Every character passes the charset check.

        But a leading hyphen fails the separate slug[0].isalnum() check.
        """
        assert validate_team_slug("-leading-hyphen") is False

    def test_hyphen_in_the_middle_is_valid(self) -> None:
        """A hyphen anywhere but position 0 is fine."""
        assert validate_team_slug("valid-slug-123") is True

    def test_uppercase_is_rejected(self) -> None:
        """isalnum() accepts uppercase, but the endpoint lowercases first.

        The pure function itself does not reject case, so this documents
        that validate_team_slug alone would accept it (endpoint-level
        lowering is what actually enforces lowercase-only slugs).
        """
        assert validate_team_slug("Has-Upper") is True


class TestCreateTeamFieldValidation:
    """create_team_endpoint's field-validation chain, run BEFORE the quota check.

    So these branches are reachable at the default (Free) tier, unlike the
    quota tests below.
    """

    @pytest.mark.asyncio
    async def test_missing_body_is_rejected(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """No JSON body 400s before any quota lookup."""
        response = await client.post("/api/v1/teams", headers=auth_headers)
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Request body required"

    @pytest.mark.asyncio
    async def test_missing_name_is_rejected(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """An empty name 400s before the slug or quota checks."""
        response = await client.post(
            "/api/v1/teams", headers=auth_headers, json={"name": "", "slug": "valid-slug"}
        )
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Team name required (1-255 chars)"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("enterprise_license")
    async def test_duplicate_slug_is_a_conflict(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """A real duplicate-slug 409, with the actual message this route sends.

        Needs enterprise_license: registration already consumes Free's
        1-team quota, so a SECOND create (even a doomed duplicate) would
        402 on the quota check before ever reaching slug uniqueness.
        """
        first = await client.post(
            "/api/v1/teams",
            headers=auth_headers,
            json={"name": "Original", "slug": "genuinely-duplicate-slug"},
        )
        assert first.status_code == 201, await first.get_json()

        second = await client.post(
            "/api/v1/teams",
            headers=auth_headers,
            json={"name": "Copycat", "slug": "genuinely-duplicate-slug"},
        )
        assert second.status_code == 409
        assert (await second.get_json())["error"] == "Team slug already exists"


class TestGetTeamDenial:
    """get_team_endpoint's own require_team_scope check."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("enterprise_license")
    async def test_non_member_is_denied(self, client: Any, auth_headers: dict[str, str]) -> None:
        """A real team, a real caller, but no membership row -> 403, not 404.

        create_team_endpoint does not enrol the creator as a member either
        (see REASON_OWNER_NOT_AUTO_MEMBER in test_teams.py), so even the
        team's own creator is denied here -- this documents that behaviour
        directly rather than relying on a second, unrelated user.
        enterprise_license only lifts the team-count wall so this SECOND
        create (registration already consumed the Free-tier quota with a
        personal team) can succeed at all.
        """
        created = await client.post(
            "/api/v1/teams",
            headers=auth_headers,
            json={"name": "Owner Only", "slug": "get-team-denial-target"},
        )
        assert created.status_code == 201
        team_id = (await created.get_json())["id"]

        response = await client.get(f"/api/v1/teams/{team_id}", headers=auth_headers)
        assert response.status_code == 403


class TestCreateTeamQuotaRefusal:
    """create_team_endpoint's deployment-wide teams quota."""

    @pytest.mark.asyncio
    async def test_second_team_on_free_tier_is_refused(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Registration already consumes Free's 1-team quota with a personal team.

        See app/auth.py:register -- the very next create attempt for this
        account must be refused, not silently create a second team.
        """
        response = await client.post(
            "/api/v1/teams",
            headers=auth_headers,
            json={"name": "One Too Many", "slug": "one-too-many-team"},
        )
        assert response.status_code == 402
        body = await response.get_json()
        assert body["dimension"] == "teams"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("enterprise_license")
    async def test_enterprise_tier_is_not_capped(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """The same account, licensed Enterprise, is not refused a 2nd team.

        Proves the refusal above is genuinely tier-gated, not a bug that
        refuses every second team unconditionally.
        """
        response = await client.post(
            "/api/v1/teams",
            headers=auth_headers,
            json={"name": "Second Team Enterprise", "slug": "second-team-enterprise"},
        )
        assert response.status_code == 201


class TestUpdateTeamFieldPresence:
    """update_team_endpoint's per-field update_data construction."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("enterprise_license")
    async def test_body_without_a_name_key_leaves_the_team_unchanged(
        self, app: Quart, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """A PUT body with no "name" key at all skips the name branch entirely.

        Distinct from test_team_membership_management.py's "name too long"
        case, which DOES enter that branch and fails the inner length
        check instead.
        """
        team_id, _owner_id = await _make_owned_team(
            client, app, auth_headers, slug="tt-no-name-key"
        )

        response = await client.put(
            f"/api/v1/teams/{team_id}", headers=auth_headers, json={"unrelated_field": "x"}
        )
        assert response.status_code == 200
        assert (await response.get_json())["name"] == "Membership Test Team"
