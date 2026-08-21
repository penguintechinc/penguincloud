"""The webui and the Nest adapter must address Nest's collections identically.

The Gough counterpart of this file (``test_gough_webui_paths.py``) exists
because Phase 4G shipped three empty tables: the browser and the adapter each
spelled a collection path for themselves and disagreed by one trailing slash,
and every test on both sides asserted against its own spelling.

Nest's shape is the mirror image of Gough's — it registers **every** route
WITHOUT a trailing slash — so the same defect here would land the other way
round: a path with a slash Nest does not declare gets a flat 404, and the
portal transport does not follow redirects, so it reads as an empty table.

The expected values below are not transcribed. They are built with the
adapter's own :func:`~app.adapters.nest.routes.tenant_path`, so the assertion
compares the browser's strings against the function that produces the
adapter's — one source, as the module docstring of ``routes.py`` requires.

The TypeScript is read as text for the same reason the Gough guard does it:
importing it would need a JS runtime in the Python suite.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest
from app.adapters.base import TENANT_PLACEHOLDER
from app.adapters.nest.mapping import (
    COLLECTION_ENVELOPE_KEYS,
    KIND_DATABASE,
    KIND_SNAPSHOT,
)
from app.adapters.nest.routes import (
    COLLECTION_COST_REPORT,
    COLLECTION_DATA_RESOURCES,
    COLLECTION_SNAPSHOTS,
    COST_SUMMARY_SEGMENT,
    NEST_ROUTE_ALLOWLIST,
    tenant_path,
)

#: Repo root, resolved from this file so the test does not depend on cwd.
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

_WEBUI_PATHS_TS: Final[Path] = (
    _REPO_ROOT / "services" / "webui" / "src" / "client" / "api" / "resources" / "nestPaths.ts"
)

#: ``key: "value",`` inside the exported object literal.
_ENTRY_RE: Final[re.Pattern[str]] = re.compile(
    r'^\s*(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*"(?P<value>[^"]+)"\s*,?\s*$'
)

#: What each webui key must equal, built from the adapter's own path builder.
_EXPECTED: Final[dict[str, str]] = {
    "databases": tenant_path(TENANT_PLACEHOLDER, COLLECTION_DATA_RESOURCES),
    "snapshots": tenant_path(TENANT_PLACEHOLDER, COLLECTION_SNAPSHOTS),
    "costReport": tenant_path(TENANT_PLACEHOLDER, COLLECTION_COST_REPORT),
    "costSummary": tenant_path(TENANT_PLACEHOLDER, COLLECTION_COST_REPORT, COST_SUMMARY_SEGMENT),
}


#: Which portal kind each webui collection key corresponds to. Only the two
#: the screens fetch as collections appear — cost report and summary are not
#: resource collections and carry a different envelope entirely.
_WEBUI_KEY_KINDS: Final[dict[str, str]] = {
    "databases": KIND_DATABASE,
    "snapshots": KIND_SNAPSHOT,
}


def _ts_object(name: str) -> dict[str, str]:
    """Parse one exported ``as const`` string object out of the TypeScript."""
    source = _WEBUI_PATHS_TS.read_text(encoding="utf-8")
    match = re.search(
        rf"export const {name}\s*=\s*\{{(?P<body>.*?)\}}\s*as const;",
        source,
        re.DOTALL,
    )
    assert match is not None, (
        f"{name} object literal not found in {_WEBUI_PATHS_TS}. If it was "
        f"renamed or restructured, update this parser — do not delete the "
        f"assertion, it is the only thing tying the two sides together."
    )
    entries: dict[str, str] = {}
    for line in match.group("body").splitlines():
        entry = _ENTRY_RE.match(line)
        if entry:
            entries[entry.group("key")] = entry.group("value")
    assert entries, f"parsed {name} but found no entries"
    return entries


def _webui_collection_paths() -> dict[str, str]:
    """Parse ``NEST_COLLECTION_PATHS`` out of the TypeScript source."""
    return _ts_object("NEST_COLLECTION_PATHS")


def _webui_envelope_keys() -> dict[str, str]:
    """Parse ``NEST_COLLECTION_ENVELOPE_KEYS`` out of the TypeScript source."""
    return _ts_object("NEST_COLLECTION_ENVELOPE_KEYS")


def test_webui_constant_file_exists() -> None:
    """The shared constant must be where the guard expects it."""
    assert _WEBUI_PATHS_TS.is_file(), f"missing {_WEBUI_PATHS_TS}"


def test_webui_declares_exactly_the_collections_its_screens_fetch() -> None:
    """Pin the set, so an unused constant cannot quietly appear.

    A declared path no screen requests is a guard over a request that is never
    made — coverage a reader would reasonably mistake for the real thing.
    """
    assert set(_webui_collection_paths()) == set(_EXPECTED)


@pytest.mark.parametrize("key", sorted(_EXPECTED))
def test_webui_path_matches_the_adapter_builder(key: str) -> None:
    """The browser and the adapter must address a collection identically.

    The webui path is proxy-relative (no leading slash); the adapter's is
    absolute. Normalising one leading slash is the only permitted difference —
    in particular a TRAILING slash must not appear, since that is the byte
    Nest answers with a 404 rather than a redirect.
    """
    webui = _webui_collection_paths()[key]
    assert not webui.startswith(
        "/"
    ), f"webui path for {key!r} must be proxy-relative, got {webui!r}"
    assert not webui.endswith(
        "/"
    ), f"nest registers no route with a trailing slash, but {key!r} sends {webui!r}"
    assert f"/{webui}" == _EXPECTED[key], (
        f"webui sends {webui!r} but the adapter builds {_EXPECTED[key]!r} " f"for {key!r}"
    )


@pytest.mark.parametrize("key", sorted(_EXPECTED))
def test_every_webui_path_is_allowlisted_for_the_proxy(key: str) -> None:
    """A path the browser sends must be one the proxy would admit.

    The rules carry ``{tenant}`` verbatim and are matched BEFORE substitution,
    so the literal placeholder is what has to match here — exactly as the
    browser sends it.
    """
    path = f"/{_webui_collection_paths()[key]}"

    assert any(
        rule.matches("GET", path) for rule in NEST_ROUTE_ALLOWLIST
    ), f"no GET RouteRule admits the {key!r} path {path!r}"


@pytest.mark.parametrize("key", sorted(_WEBUI_KEY_KINDS))
def test_webui_envelope_key_matches_the_adapters(key: str) -> None:
    """The browser and the adapter must unwrap a collection identically.

    Nest names a different key per collection and only data-resources uses
    ``items``. Both sides read ``items`` for everything and fell back to an
    empty list, so the Snapshots tab reported "No snapshots have been taken
    from this resource" whatever Nest answered — with nothing failing. The
    adapter's table is bound to Nest's own handlers in
    ``test_nest_source_fixture.py``; this ties the browser's to the adapter's,
    so the chain terminates at Nest on both sides.
    """
    webui = _webui_envelope_keys()

    assert key in webui, f"the webui declares no envelope key for {key!r}"
    assert webui[key] == COLLECTION_ENVELOPE_KEYS[_WEBUI_KEY_KINDS[key]], (
        f"webui unwraps {key!r} from {webui[key]!r} but the adapter uses "
        f"{COLLECTION_ENVELOPE_KEYS[_WEBUI_KEY_KINDS[key]]!r}"
    )


def test_webui_declares_an_envelope_key_for_every_collection_it_lists() -> None:
    """A fetched collection with no declared key would decode as nothing.

    Pinned as an exact set so a new collection cannot be added on one side
    only — which is how the two sides drifted the first time.
    """
    assert set(_webui_envelope_keys()) == set(_WEBUI_KEY_KINDS)


def test_a_named_data_resource_is_allowlisted() -> None:
    """The detail path is built in TS by interpolation, so pin its shape.

    Nest addresses a DataResource by NAME in every route. A slug-shaped name
    must be admitted; the allowlist types the segment so a path-shaped value
    cannot be smuggled into the id slot.
    """
    databases = f"/{_webui_collection_paths()['databases']}"

    assert any(rule.matches("GET", f"{databases}/orders-primary") for rule in NEST_ROUTE_ALLOWLIST)
    assert not any(
        rule.matches("GET", f"{databases}/../../auth/login") for rule in NEST_ROUTE_ALLOWLIST
    )
