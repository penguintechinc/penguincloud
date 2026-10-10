"""The webui and the Tobogganing adapter must address the product identically.

The Gough counterpart of this file exists because Phase 4G shipped three empty
tables: the browser and the adapter each spelled a collection path for
themselves and disagreed by one trailing slash, and every test on both sides
asserted against its own spelling. The Nest counterpart exists because the two
sides then disagreed about the ENVELOPE KEY instead, and three collections
decoded as permanently empty while the UI stated it to the operator as fact.

Tobogganing can fail in **both** ways at once, harder than either predecessor:

* it registers ``GET /api/v1/clusters/`` WITH a trailing slash and
  ``GET /api/v1/sdwan/clusters`` WITHOUT, both ``strict_slashes=True`` — two
  paths that read alike with opposite requirements, so a uniform rule is wrong
  in one direction or the other; and
* **nothing in the product answers** ``items``. Every list route names its rows
  differently, so the 4N assumption would have emptied *every* Tobogganing
  table rather than three of four.

Neither side is checked against a copy of itself. The expected values are the
adapter's own constants from :mod:`app.adapters.tobogganing.routes` and
:mod:`~app.adapters.tobogganing.mapping`, which
``test_tobogganing_source_fixture.py`` in turn grades against a live boot of
Tobogganing. So the chain terminates at the product on both sides.

The TypeScript is read as text for the same reason the Gough and Nest guards do
it: importing it would need a JS runtime in the Python suite, and parsing the
literal keeps the assertion in the suite that owns the routes it compares
against.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest
from app.adapters.tobogganing.mapping import (
    COLLECTION_ENVELOPE_KEYS,
    KIND_BLOCK_PAGE,
    KIND_SDWAN_CLIENT,
    KIND_SDWAN_CLUSTER,
    KIND_SWG_POLICY,
    KIND_WIREGUARD_PEER,
)
from app.adapters.tobogganing.routes import (
    PATH_BLOCKPAGE_PAGES,
    PATH_CLUSTERS_FLAT,
    PATH_SDWAN_CLIENTS,
    PATH_SDWAN_CLUSTERS,
    PATH_SWG_POLICY,
    PATH_WIREGUARD_PEERS,
    SEGMENT_PREVIEW,
    SEGMENT_PUBLISH,
    TOBOGGANING_ROUTE_ALLOWLIST,
    blockpage_path,
)

#: Repo root, resolved from this file so the test does not depend on cwd.
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

_WEBUI_PATHS_TS: Final[Path] = (
    _REPO_ROOT
    / "services"
    / "webui"
    / "src"
    / "client"
    / "api"
    / "resources"
    / "tobogganingPaths.ts"
)

#: ``key: "value",`` inside the exported object literal.
_ENTRY_RE: Final[re.Pattern[str]] = re.compile(
    r'^\s*(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*"(?P<value>[^"]+)"\s*,?\s*$'
)

#: What each webui collection key must equal, taken from the adapter itself.
_EXPECTED_PATHS: Final[dict[str, str]] = {
    "clients": PATH_SDWAN_CLIENTS,
    "clusters": PATH_SDWAN_CLUSTERS,
    "peers": PATH_WIREGUARD_PEERS,
    "blockPages": PATH_BLOCKPAGE_PAGES,
    "swgPolicies": PATH_SWG_POLICY,
}

#: Which portal kind each webui collection key corresponds to.
_WEBUI_KEY_KINDS: Final[dict[str, str]] = {
    "clients": KIND_SDWAN_CLIENT,
    "clusters": KIND_SDWAN_CLUSTER,
    "peers": KIND_WIREGUARD_PEER,
    "blockPages": KIND_BLOCK_PAGE,
    "swgPolicies": KIND_SWG_POLICY,
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
    """Parse ``TOBOGGANING_COLLECTION_PATHS`` out of the TypeScript source."""
    return _ts_object("TOBOGGANING_COLLECTION_PATHS")


def _webui_envelope_keys() -> dict[str, str]:
    """Parse ``TOBOGGANING_COLLECTION_ENVELOPE_KEYS`` out of the TypeScript."""
    return _ts_object("TOBOGGANING_COLLECTION_ENVELOPE_KEYS")


def _ts_const(name: str) -> str:
    """Read one exported string constant out of the TypeScript source."""
    source = _WEBUI_PATHS_TS.read_text(encoding="utf-8")
    match = re.search(rf'export const {name}\s*=\s*"(?P<value>[^"]+)"', source)
    assert match is not None, f"export const {name} not found in {_WEBUI_PATHS_TS}"
    return match.group("value")


def test_webui_constant_file_exists() -> None:
    """The shared constant must be where the guard expects it."""
    assert _WEBUI_PATHS_TS.is_file(), f"missing {_WEBUI_PATHS_TS}"


def test_webui_declares_exactly_the_collections_its_screens_fetch() -> None:
    """Pin the set, so an unused constant cannot quietly appear.

    A declared path no screen requests is a guard over a request that is never
    made — coverage a reader would reasonably mistake for the real thing. It
    also keeps the machine plane out by construction: a ``firewall`` or
    ``headend`` key added here fails immediately, and those routes cannot be
    reached with a portal credential at all (``aud`` mismatch, see
    ``routes.py``).
    """
    assert set(_webui_collection_paths()) == set(_EXPECTED_PATHS)


@pytest.mark.parametrize("key", sorted(_EXPECTED_PATHS))
def test_webui_path_matches_the_adapter_constant(key: str) -> None:
    """The browser and the adapter must address a collection identically.

    The webui path is proxy-relative (no leading slash); the adapter's is
    absolute. Normalising that one leading slash is the ONLY permitted
    difference — in particular a trailing slash must not appear on any of
    these, since every one of them is registered without it and Werkzeug
    answers a flat 404 rather than redirecting back.
    """
    webui = _webui_collection_paths()[key]

    assert not webui.startswith(
        "/"
    ), f"webui path for {key!r} must be proxy-relative, got {webui!r}"
    assert f"/{webui}" == _EXPECTED_PATHS[key], (
        f"webui sends {webui!r} but the adapter builds " f"{_EXPECTED_PATHS[key]!r} for {key!r}"
    )


@pytest.mark.parametrize("key", sorted(_EXPECTED_PATHS))
def test_no_screen_path_carries_a_trailing_slash(key: str) -> None:
    """The half of the slash asymmetry these screens actually depend on.

    Asserted separately from the equality above so the reason survives: all
    five of these routes are registered WITHOUT a trailing slash, and a
    request carrying one earns a flat 404 that surfaces as an empty table.
    """
    assert not _webui_collection_paths()[key].endswith("/")


def test_the_flat_cluster_route_is_the_one_with_the_slash() -> None:
    """Falsifies the check above — a blanket "no slashes" rule would be wrong.

    ``GET /api/v1/clusters/`` IS registered with a trailing slash, and
    stripping it earns a 308 the portal transport does not follow. Pinned here
    so "no path ends in a slash" cannot be generalised into a rule that breaks
    the flat cluster route the moment a screen reaches for it.
    """
    assert PATH_CLUSTERS_FLAT.endswith("/")
    assert not PATH_SDWAN_CLUSTERS.endswith("/")
    assert PATH_CLUSTERS_FLAT.rstrip("/") != PATH_SDWAN_CLUSTERS


@pytest.mark.parametrize("key", sorted(_EXPECTED_PATHS))
def test_every_webui_path_is_allowlisted_for_the_proxy(key: str) -> None:
    """A path the browser sends must be one the deny-by-default proxy admits."""
    path = f"/{_webui_collection_paths()[key]}"

    assert any(
        rule.matches("GET", path) for rule in TOBOGGANING_ROUTE_ALLOWLIST
    ), f"no GET RouteRule admits the {key!r} path {path!r}"


@pytest.mark.parametrize("key", sorted(_WEBUI_KEY_KINDS))
def test_webui_envelope_key_matches_the_adapters(key: str) -> None:
    """The browser and the adapter must unwrap a collection identically.

    Tobogganing names a different key per collection and uses ``items`` for
    NOTHING. Both sides reading ``items`` and falling back to ``[]`` is what
    made Nest's Snapshots tab report "No snapshots have been taken from this
    resource" whatever Nest answered; here it would have emptied all five of
    these tables. The adapter's table is bound to Tobogganing's own handlers in
    ``test_tobogganing_source_fixture.py``; this ties the browser's to the
    adapter's, so the chain ends at the product on both sides.
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


def test_no_webui_collection_is_unwrapped_from_items() -> None:
    """The 4N defect, named directly rather than left to the equality above.

    If someone "simplified" both tables to ``items`` at once, the per-key
    comparison would still pass — it only proves the two sides agree. This
    proves they agree on something the product actually emits.
    """
    assert "items" not in set(_webui_envelope_keys().values())
    assert "items" not in set(COLLECTION_ENVELOPE_KEYS.values())


def test_block_page_item_paths_are_allowlisted() -> None:
    """The block-page verbs address one page by id, built by interpolation.

    The id slot is typed as a UUID by the allowlist, which is the honest shape
    (pages are named ``str(uuid.uuid4())``) and, unlike a permissive pattern,
    structurally incapable of matching the literal ``preview``/``publish``
    sub-collections.
    """
    page_id = "3f1b8a2e-9c4d-4f7a-8b21-0d5e6c7a8b90"
    pages = f"/{_webui_collection_paths()['blockPages']}"

    assert any(rule.matches("PUT", f"{pages}/{page_id}") for rule in TOBOGGANING_ROUTE_ALLOWLIST)
    for segment in (SEGMENT_PREVIEW, SEGMENT_PUBLISH):
        assert any(
            rule.matches("POST", f"{pages}/{page_id}/{segment}")
            for rule in TOBOGGANING_ROUTE_ALLOWLIST
        ), segment


def test_the_webui_block_page_segments_match_the_adapters() -> None:
    """Both sides must spell ``preview``/``publish`` the same way.

    They are literals in two languages; a typo on the webui side would build a
    path the allowlist refuses, which the operator sees as a failed publish
    with no explanation.
    """
    assert _ts_const("BLOCK_PAGE_SEGMENT_PREVIEW") == SEGMENT_PREVIEW
    assert _ts_const("BLOCK_PAGE_SEGMENT_PUBLISH") == SEGMENT_PUBLISH


def test_a_path_shaped_page_id_is_refused() -> None:
    """The id slot must not admit traversal into another route.

    The browser encodes the id too, but that is the near end of the rule; this
    is the end that holds when the caller is not the browser.
    """
    pages = f"/{_webui_collection_paths()['blockPages']}"

    assert not any(
        rule.matches("PUT", f"{pages}/../../auth/login") for rule in TOBOGGANING_ROUTE_ALLOWLIST
    )


def test_the_blockpage_builder_agrees_with_the_webui_shape() -> None:
    """The adapter's own builder must produce what the browser sends.

    Compared through ``blockpage_path`` rather than a literal, so a change to
    the adapter's path construction fails here instead of at runtime.
    """
    page_id = "3f1b8a2e-9c4d-4f7a-8b21-0d5e6c7a8b90"
    pages = _webui_collection_paths()["blockPages"]

    assert f"/{pages}/{page_id}" == blockpage_path(page_id)
    assert f"/{pages}/{page_id}/{SEGMENT_PUBLISH}" == blockpage_path(page_id, SEGMENT_PUBLISH)


def test_no_machine_plane_path_reached_the_webui() -> None:
    """The load-bearing finding of Session 1, asserted rather than remembered.

    Firewall rules, the flat WireGuard peer list and headend ports are guarded
    by ``@require_machine_jwt``, which rejects any token whose ``aud`` is not
    ``"headend"``. A portal credential carries ``aud=="tobogganing"``, so no
    screen can ever be backed by one — this is an audience mismatch, not a
    scope one, and no amount of scope grants fixes it.

    Named as substrings rather than as exact paths because the failure this
    prevents is a screen reaching for ``api/v1/wireguard/peers`` (machine) when
    it means ``api/v1/sdwan/wireguard/peers`` (user) — one segment apart.
    """
    sent = set(_webui_collection_paths().values())

    assert "api/v1/firewall/rules" not in sent
    assert "api/v1/wireguard/peers" not in sent, (
        "that is the MACHINE-plane peer list (aud=='headend'); the "
        "user-reachable one is api/v1/sdwan/wireguard/peers"
    )
    assert not any(path.startswith("api/v1/headend/") for path in sent)
    assert "api/v1/sdwan/status" not in sent, (
        "sdwan/status carries no auth decorator and hardcodes tenant_id="
        "'default' — proxying it leaks one tenant's fleet size to all others"
    )
