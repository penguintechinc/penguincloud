"""The webui and the adapter must address Gough's collections identically.

Why this file exists
====================
Phase 4G shipped with the browser calling ``api/v1/nodes`` while the adapter
called ``/api/v1/nodes/``. Both "looked right" in review and both had test
coverage, because each side was asserted against *itself*: the jest suite
pinned ``expect(forwardedPath()).toBe("api/v1/nodes")`` — the broken value —
and the Python suite exercised the adapter through a fake that routed exactly
what the adapter sent. Neither could fail.

The property no single-sided test can express is that the two agree, and that
both match what Gough actually registers. Gough's route table is asymmetric:

* ``nodes_bp.route("/")``, ``biomes_bp.route("/")``, ``agents_bp.route("/")``
  — trailing slash present.
* ``biomes_bp.route("/groups")`` — trailing slash ABSENT.

``strict_slashes`` is never set, so Werkzeug's default applies and it only
redirects one way: a missing slash yields 308, an extra one yields a bare 404.
The portal's transport does not follow redirects and the proxy strips
``location``, so BOTH failure modes surface to the user as an empty table
rather than an error.

This test reads the TypeScript constant as text on purpose. Importing it would
need a JS runtime in the Python suite; parsing the literal keeps the assertion
in the same suite as the adapter it is comparing against, and a drift in either
file turns it red.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest
from app.adapters.gough.adapter import _COLLECTION_ROUTES

#: Repo root, resolved from this file so the test does not depend on cwd.
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

_WEBUI_PATHS_TS: Final[Path] = (
    _REPO_ROOT / "services" / "webui" / "src" / "client" / "api" / "resources" / "goughPaths.ts"
)

#: ``key: "value",`` inside the exported object literal.
_ENTRY_RE: Final[re.Pattern[str]] = re.compile(
    r'^\s*(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*"(?P<value>[^"]+)"\s*,?\s*$'
)


def _webui_collection_paths() -> dict[str, str]:
    """Parse ``GOUGH_COLLECTION_PATHS`` out of the TypeScript source."""
    source = _WEBUI_PATHS_TS.read_text(encoding="utf-8")
    match = re.search(
        r"export const GOUGH_COLLECTION_PATHS\s*=\s*\{(?P<body>.*?)\}\s*as const;",
        source,
        re.DOTALL,
    )
    assert match is not None, (
        f"GOUGH_COLLECTION_PATHS object literal not found in {_WEBUI_PATHS_TS}. "
        f"If it was renamed or restructured, update this parser — do not delete "
        f"the assertion, it is the only thing tying the two sides together."
    )
    paths: dict[str, str] = {}
    for line in match.group("body").splitlines():
        entry = _ENTRY_RE.match(line)
        if entry:
            paths[entry.group("key")] = entry.group("value")
    assert paths, "parsed GOUGH_COLLECTION_PATHS but found no entries"
    return paths


def test_webui_constant_file_exists() -> None:
    """The shared constant must be where the guard expects it."""
    assert _WEBUI_PATHS_TS.is_file(), f"missing {_WEBUI_PATHS_TS}"


def test_webui_collections_are_a_subset_the_adapter_knows() -> None:
    """Every collection the browser requests must exist adapter-side.

    A subset, not equality. The webui constant lists only what the BROWSER
    actually fetches; the adapter also addresses ``biome_groups``
    server-side, which no screen requests. Declaring it on the webui side
    would be a guard over a request that is never made — coverage a reader
    would reasonably mistake for the real thing.

    The direction that matters is still asserted: a webui path with no
    adapter counterpart is a path nothing validates.
    """
    webui = set(_webui_collection_paths())
    assert webui, "the webui must declare at least one collection"
    assert webui <= set(_COLLECTION_ROUTES), (
        f"webui declares collections the adapter does not know: "
        f"{sorted(webui - set(_COLLECTION_ROUTES))}"
    )


def test_webui_declares_exactly_the_collections_its_screens_fetch() -> None:
    """Pin the set, so an unused constant cannot quietly reappear.

    ``biome_groups`` was declared here and never requested. Asserting the
    exact set means adding one is a deliberate edit to this test rather than
    a dead guard nobody notices.
    """
    assert set(_webui_collection_paths()) == {"nodes", "biomes", "agents"}


@pytest.mark.parametrize("kind", sorted(_webui_collection_paths()))
def test_webui_path_matches_adapter_path(kind: str) -> None:
    """The browser and the adapter must address a collection identically.

    The webui path is proxy-relative (no leading slash); the adapter path is
    absolute. Normalising one leading slash is the only permitted difference —
    in particular the TRAILING slash must match exactly, since that is the
    byte the 308/404 turns on.
    """
    webui = _webui_collection_paths()[kind]
    assert not webui.startswith(
        "/"
    ), f"webui path for {kind!r} must be proxy-relative, got {webui!r}"
    assert f"/{webui}" == _COLLECTION_ROUTES[kind], (
        f"webui sends {webui!r} but the adapter sends " f"{_COLLECTION_ROUTES[kind]!r} for {kind!r}"
    )


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("nodes", "/api/v1/nodes/"),
        ("biomes", "/api/v1/biomes/"),
        ("agents", "/api/v1/agents/"),
        ("biome_groups", "/api/v1/biomes/groups"),
    ],
)
def test_adapter_matches_goughs_real_route_shape(kind: str, expected: str) -> None:
    """Pin the shapes against Gough's own route registrations.

    Transcribed from ``services/api-manager/app/api/{nodes,biomes,agents}.py``
    in the Gough repo, not from its committed OpenAPI spec — that spec
    documents routes the service does not register.

    ``biome_groups`` is the one WITHOUT a trailing slash and is the case the
    adapter got wrong in the other direction: it sent
    ``/api/v1/biomes/groups/``, which Werkzeug answers with a 404 and no
    redirect back.
    """
    assert _COLLECTION_ROUTES[kind] == expected


def test_every_collection_route_is_allowlisted_for_the_proxy() -> None:
    """A path the adapter uses must also be one the proxy would admit.

    The adapter is the trusted path and is not filtered by the allowlist, but
    the webui reaches these same collections THROUGH the proxy. A shape the
    allowlist rejects is a 403 for the browser even when the adapter is right.
    """
    from app.adapters.gough.routes import GOUGH_ROUTE_ALLOWLIST

    for kind, path in _COLLECTION_ROUTES.items():
        assert any(
            rule.matches("GET", path) for rule in GOUGH_ROUTE_ALLOWLIST
        ), f"no GET RouteRule admits the {kind!r} collection path {path!r}"
