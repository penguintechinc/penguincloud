"""Bind the portal's Nest assumptions to Nest's own source, everywhere.

Two things are asserted here and they answer different failure modes.

**The per-kind envelope keys.** Nest has no shared collection envelope: only
``data-resources`` answers ``items``, while snapshots answer ``snapshots``,
protection policies ``policies`` and search pools ``searchPools``. The adapter
read ``items`` for all four and returned ``[]`` when it was absent, so three of
the four kinds decoded as permanently empty — and the Snapshots tab stated that
to the operator as fact ("No snapshots have been taken from this resource").
Nothing failed anywhere. The table in ``mapping.py`` is therefore compared here
against the keys parsed out of Nest's handlers, so it is graded by Nest rather
than by the comment above it.

**The vendored fixture's freshness.** Those keys, and the route table the
allowlist guards bind against, are vendored into ``tests/api/fixtures`` so the
checks run on a machine with no Nest checkout. A vendored copy that silently
rots is worse than no copy, so wherever a checkout *does* exist the committed
JSON is compared against a live parse and a difference is a red build with the
refresh command in the message.
"""

from __future__ import annotations

from typing import Final

import pytest
from app.adapters.nest.mapping import (
    COLLECTION_ENVELOPE_KEYS,
    NEST_LIST_HANDLERS,
    RESOURCE_KINDS,
    envelope_key,
)
from nest_route_source import (
    FIXTURE_NAME,
    effective_envelope_keys,
    envelope_keys,
    missing_reason,
    nest_api_module,
    nest_handlers_dir,
    route_table,
    vendored_envelope_keys,
    vendored_route_table,
)
from product_source_fixtures import (
    MAX_FIXTURE_AGE_DAYS,
    describe_mapping_drift,
    describe_route_drift,
    fixture_age_days,
    fixture_path,
    load_fixture,
    source_required,
)

#: Refresh instruction, quoted in every drift message so the fix is in the
#: failure rather than in a wiki page.
_REFRESH: Final[str] = "make refresh-product-source-fixtures"


def _skip_or_fail(reason: str) -> None:
    """Skip for a missing checkout — unless the job declared it has one.

    ``REQUIRE_PRODUCT_SOURCE=1`` turns "no checkout, skipping" into a failure,
    so a job that is supposed to have the checkouts reports a missing one
    rather than quietly covering less than it claims.
    """
    if source_required():
        pytest.fail(reason)
    pytest.skip(reason)


class TestEnvelopeKeys:
    """The per-kind table is Nest's, not the portal's."""

    def test_the_fixture_is_committed(self) -> None:
        """Without it, every check below degrades to a skip on a CI runner."""
        assert fixture_path(
            FIXTURE_NAME
        ).is_file(), f"{fixture_path(FIXTURE_NAME)} is missing — run `{_REFRESH}`"

    def test_every_kind_declares_an_envelope_key(self) -> None:
        """A kind with no key would raise, not decode as empty — but loudly.

        Asserted anyway: the failure should be "this kind was never looked up"
        at import time, not a 500 the first time an operator opens the screen.
        """
        assert set(COLLECTION_ENVELOPE_KEYS) == set(RESOURCE_KINDS)
        assert set(NEST_LIST_HANDLERS) == set(RESOURCE_KINDS)

    def test_only_data_resources_uses_the_items_envelope(self) -> None:
        """Pin the asymmetry itself, so a "tidy-up" to one key fails here.

        The defect was not a typo — it was the assumption that one envelope
        covered every collection. Stating the asymmetry as a test is what
        stops it being re-assumed.
        """
        by_key: dict[str, list[str]] = {}
        for kind, key in COLLECTION_ENVELOPE_KEYS.items():
            by_key.setdefault(key, []).append(kind)

        assert by_key["items"] == ["database"]
        assert len(by_key) == 4, f"expected four distinct keys, got {by_key!r}"

    @pytest.mark.parametrize("kind", sorted(RESOURCE_KINDS))
    def test_each_key_is_the_one_nests_handler_emits(self, kind: str) -> None:
        """Graded by Nest's source (or its vendored parse), not by a comment.

        Renaming ``snapshots`` in Nest's handler, or mis-assigning a kind to
        another kind's key, both fail here.
        """
        nest_keys = effective_envelope_keys()
        handler = NEST_LIST_HANDLERS[kind]

        assert handler in nest_keys, (
            f"nest no longer defines a list handler named {handler!r} "
            f"(found {sorted(nest_keys)!r}) — the {kind!r} envelope key can no "
            f"longer be verified. If Nest renamed it, update NEST_LIST_HANDLERS "
            f"and run `{_REFRESH}`."
        )
        assert envelope_key(kind) == nest_keys[handler], (
            f"{kind!r} is decoded from {envelope_key(kind)!r} but nest's "
            f"{handler} emits {nest_keys[handler]!r} — the collection would "
            f"decode as empty and render as 'none'."
        )


class TestFixtureFreshness:
    """The vendored copy must still be what the product's source says."""

    def test_vendored_routes_match_a_live_parse(self) -> None:
        """A fixture that rots silently is worse than no fixture."""
        if nest_api_module() is None:
            _skip_or_fail(missing_reason())

        vendored, live = vendored_route_table(), route_table()
        assert vendored == live, (
            f"the vendored nest route table ({fixture_path(FIXTURE_NAME)}) no "
            f"longer matches Nest's source. Run `{_REFRESH}` and review the "
            f"diff — a route Nest added, renamed or retired changes what the "
            f"allowlist guards are graded against.\n"
            f"{describe_route_drift(vendored, live)}"
        )

    def test_vendored_envelope_keys_match_a_live_parse(self) -> None:
        """Same, for the keys the collections decode from."""
        if nest_handlers_dir() is None:
            _skip_or_fail(missing_reason())

        vendored, live = vendored_envelope_keys(), envelope_keys()
        assert vendored == live, (
            f"the vendored nest envelope keys ({fixture_path(FIXTURE_NAME)}) "
            f"no longer match Nest's handlers. Run `{_REFRESH}` and review "
            f"the diff.\n{describe_mapping_drift('handler', vendored, live)}"
        )

    def test_the_fixture_records_where_it_came_from(self) -> None:
        """Provenance is what makes a stale fixture diagnosable at all.

        Without it, a vendored table on a machine with no checkout is a claim
        with no date and no origin — and the plausibility floors below catch
        TRUNCATION, not rot. The commit sha additionally distinguishes "nobody
        refreshed this" from "someone refreshed it against an old checkout",
        which look identical from the date alone.
        """
        payload = load_fixture(FIXTURE_NAME)

        assert payload.get("generated_on"), f"no generation date — run `{_REFRESH}`"
        assert payload.get("source_commit"), (
            f"no source commit recorded — run `{_REFRESH}` from a git checkout "
            f"so a stale-but-recently-regenerated fixture stays diagnosable"
        )

    def test_the_fixture_is_within_the_staleness_budget(self) -> None:
        """A table nobody has refreshed stops being quietly trusted.

        This is the half of the guard that works WITHOUT a checkout, which is
        the case the vendoring exists for: with no Nest on disk there is
        nothing to diff against, so age is the only signal available that the
        product may have moved underneath it.

        Raising the budget to silence this defeats it — refresh the fixture,
        which is one make target. See who runs it, and when, in
        task-4N-report.md §Fix round 2.
        """
        age = fixture_age_days(FIXTURE_NAME)

        assert age is not None, (
            f"the vendored nest fixture records no generation date, so its "
            f"staleness cannot be judged at all — run `{_REFRESH}`"
        )
        assert age <= MAX_FIXTURE_AGE_DAYS, (
            f"the vendored nest route table was generated {age} days ago "
            f"(budget {MAX_FIXTURE_AGE_DAYS}). Nest may have moved underneath "
            f"every guard built on it. Run `{_REFRESH}`."
        )

    def test_the_vendored_route_table_is_plausible(self) -> None:
        """Guard the fallback itself against being emptied.

        Every allowlist guard binds against this table when no checkout is
        present. A truncated fixture would make them all pass vacuously — the
        exact failure mode the skip already had.
        """
        table = vendored_route_table()

        assert len(table) >= 19, (
            f"the vendored nest route table has only {len(table)} paths; Nest "
            f"declares 27 registrations across 21 distinct paths. Run "
            f"`{_REFRESH}`."
        )
        assert "/api/v1/tenants/<tenant_id>/data-resources" in table
