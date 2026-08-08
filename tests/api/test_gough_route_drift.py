"""Detect Gough moving a route out from under the adapter.

``FakeGough`` answers with Gough's real routing semantics — 308 for a missing
trailing slash, flat 404 for an undeclared one — because it drives a genuine
:class:`werkzeug.routing.Map` built from ``_GOUGH_REAL_ROUTES``. That table is
a **hand transcription**, and a hand transcription rots silently: if Gough
renames ``/api/v1/biomes/groups``, drops a method, or adds a trailing slash,
every test in ``test_gough_adapter.py`` keeps passing against a Gough that no
longer exists. The fake would agree with the adapter about a fiction.

This module is the only thing standing between that transcription and reality.
It parses Gough's own route registrations out of its source
(:mod:`tests.api.gough_route_source`) and asserts the transcription still
matches — so a route change in Gough turns this suite red instead of being
discovered in production.

Scope: the transcription is a deliberate SUBSET of Gough's ~154 routes (the
ones the adapter depends on), so these tests assert *subset agreement* — every
transcribed route must still exist in Gough exactly as written. Routes Gough
adds elsewhere are not the fake's business and do not fail anything.

Skipping: CI runners have no Gough checkout, so every test here skips with a
reason naming the path it looked for and the environment variable that
redirects it. A silent pass would be worse than no test at all.
"""

from __future__ import annotations

from typing import Final

import pytest

from app.adapters.gough.adapter import _COLLECTION_ROUTES

from gough_route_source import (
    gough_app_root,
    gough_source_routes,
    missing_reason,
)
from test_gough_adapter import _GOUGH_REAL_ROUTES

pytestmark = pytest.mark.skipif(
    gough_app_root() is None,
    reason=missing_reason(),
)

#: Below this, assume the parser broke rather than that Gough shrank. Without
#: it, a parser returning ``{}`` would make every "is this route still there?"
#: assertion fail loudly — but a parser returning a handful of routes could
#: still let a narrowed comparison look healthy. Gough registers ~154 routes
#: across 20-odd blueprints; 100 is a floor no real refactor crosses.
_MIN_PLAUSIBLE_ROUTES: Final[int] = 100


@pytest.fixture(scope="module")
def gough_routes() -> dict[str, frozenset[str]]:
    """Gough's registered routes, parsed from its source tree."""
    return gough_source_routes()


def test_parser_finds_a_plausible_route_table(
    gough_routes: dict[str, frozenset[str]],
) -> None:
    """Guard against a broken parser making the other tests vacuous.

    Every assertion below is of the form "this transcribed route still exists".
    A parser that silently stopped finding decorators would fail them all, but
    it would fail them with a confusing message about Gough deleting its entire
    API. This makes the real cause the first failure you see.
    """
    assert len(gough_routes) >= _MIN_PLAUSIBLE_ROUTES, (
        f"parsed only {len(gough_routes)} routes from Gough's source; expected "
        f">= {_MIN_PLAUSIBLE_ROUTES}. The parser in gough_route_source.py has "
        f"probably broken (a changed decorator or Blueprint spelling), rather "
        f"than Gough having deleted its API."
    )


@pytest.mark.parametrize(("path", "methods"), _GOUGH_REAL_ROUTES)
def test_transcribed_route_still_exists_in_gough(
    path: str,
    methods: tuple[str, ...],
    gough_routes: dict[str, frozenset[str]],
) -> None:
    """Each route FakeGough models is still registered by Gough, as written.

    Fails when Gough renames a route, removes it, or changes its trailing
    slash — the last being the defect that shipped: the adapter requested
    ``/api/v1/biomes/groups/`` against a route registered without the slash and
    got a flat 404 with no redirect, rendering an empty table.

    The path comparison is deliberately byte-exact for that reason. Anything
    that normalised slashes before comparing would be blind to the whole class
    of bug this file exists to catch.
    """
    if path not in gough_routes:
        near = sorted(p for p in gough_routes if p.rstrip("/") == path.rstrip("/"))
        hint = (
            f" Gough registers {near!r} — the difference is the trailing slash, "
            f"which is a 308-vs-404 change, not a cosmetic one."
            if near
            else " No similarly-named route exists; it was renamed or removed."
        )
        pytest.fail(
            f"_GOUGH_REAL_ROUTES claims Gough registers {path!r}, but it does "
            f"not.{hint} Update the transcription in test_gough_adapter.py AND "
            f"check whether the adapter still addresses the right path."
        )

    assert gough_routes[path] == frozenset(methods), (
        f"method drift on {path!r}: FakeGough models {sorted(methods)}, Gough "
        f"registers {sorted(gough_routes[path])}. FakeGough decides 405-vs-match "
        f"from this set, so a mismatch makes every test using it unreliable."
    )


@pytest.mark.parametrize(("kind", "route"), sorted(_COLLECTION_ROUTES.items()))
def test_adapter_collection_route_is_one_gough_really_registers(
    kind: str,
    route: str,
    gough_routes: dict[str, frozenset[str]],
) -> None:
    """The adapter's OWN collection paths, checked against Gough's source.

    This is the assertion that would have caught the original defect at its
    source rather than at the test double. ``_COLLECTION_ROUTES`` is the table
    the adapter actually builds URLs from, and its entries differ from one
    another precisely in the trailing slash (``/api/v1/nodes/`` but
    ``/api/v1/biomes/groups``). Checking the fake alone leaves the adapter's
    real table unverified.
    """
    assert route in gough_routes, (
        f"the gough adapter lists {route!r} as the collection route for "
        f"{kind!r}, but Gough registers no such route. Requests will 404 (or "
        f"308 into a stripped redirect) and the {kind} table will render empty."
    )
    assert "GET" in gough_routes[route], (
        f"{route!r} exists but Gough does not serve GET on it; "
        f"list_resources({kind!r}) cannot work."
    )


def test_trailing_slash_asymmetry_is_still_real(
    gough_routes: dict[str, frozenset[str]],
) -> None:
    """Pin the specific asymmetry the adapter encodes, both directions.

    The adapter hard-codes that node/biome/agent collections carry a trailing
    slash while ``biomes/groups`` does not. If Gough ever makes them uniform,
    this fails and tells whoever changed it that ``_COLLECTION_ROUTES`` is now
    wrong in the opposite direction — a case a per-route existence check would
    report as a bare missing path with no explanation.
    """
    for slashed in ("/api/v1/nodes/", "/api/v1/biomes/", "/api/v1/agents/"):
        assert slashed in gough_routes, f"{slashed} lost its trailing slash"
        assert slashed.rstrip("/") not in gough_routes, (
            f"Gough now ALSO registers {slashed.rstrip('/')!r}; the 308 "
            f"redirect this adapter avoids no longer applies and "
            f"_COLLECTION_ROUTES can be simplified."
        )

    assert "/api/v1/biomes/groups" in gough_routes
    assert "/api/v1/biomes/groups/" not in gough_routes, (
        "Gough now registers /api/v1/biomes/groups/ WITH a trailing slash; "
        "_COLLECTION_ROUTES['biome_groups'] must gain one too."
    )
