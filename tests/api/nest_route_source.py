"""Parse Nest's real route registrations straight out of its source tree.

Same purpose and same shape as :mod:`tests.api.gough_route_source`, for the
other half of the reason 4G needed one: a fake that answers whatever the
adapter asks cannot falsify the adapter, and a hand-transcribed route table
goes stale silently. Deriving Nest's table from Nest's own source lets
``test_nest_allowlist.py`` assert that every path this adapter builds is a
path Nest really registers — including the trailing-slash shape, which no
spec records.

Why an AST parse rather than importing Nest
===========================================
Importing ``nest.apps.api.app`` would need Nest's whole dependency set
(``quart``, ``aiohttp``, ``jwt``, ``prometheus_client``, its own
``middleware``/``handlers`` packages resolved as top-level modules) inside the
portal's interpreter. :mod:`ast` needs only the file on disk, so this runs
wherever a Nest checkout exists and skips cleanly where none does.

Nest is simpler to parse than Gough: ``apps/api/app.py`` registers every
route with a bare ``@app.route(...)`` inside ``create_app`` — no blueprints,
no prefixes to join, so the decorator's first argument IS the final path.
That is itself worth asserting, and :func:`route_table` fails loudly rather
than silently returning a short list if the file stops looking like that.

Trailing slashes
================
Every one of Nest's registrations is written without a trailing slash. Under
Werkzeug's default ``strict_slashes`` that makes a trailing-slash request a
flat 404 with no redirect back — the portal's transport does not follow
redirects and the proxy strips ``location``, so it would surface as an empty
table rather than an error. The parse preserves the exact registered string
so a test can assert on it instead of trusting this paragraph.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any, Final

from product_source_fixtures import (
    load_fixture,
    method_map,
    provenance,
    unmethod_map,
    write_fixture,
)

__all__ = [
    "DEFAULT_NEST_ROOT",
    "NEST_ROOT_ENV_VAR",
    "FIXTURE_NAME",
    "nest_api_module",
    "nest_handlers_dir",
    "missing_reason",
    "route_table",
    "envelope_keys",
    "vendored_route_table",
    "vendored_envelope_keys",
    "effective_route_table",
    "effective_envelope_keys",
    "build_fixture",
]

#: Where a Nest checkout normally lives on a PenguinTech dev machine.
DEFAULT_NEST_ROOT: Final[Path] = Path("/home/penguin/code/nest")

#: Override for a checkout somewhere else.
NEST_ROOT_ENV_VAR: Final[str] = "NEST_SOURCE_ROOT"

#: Stem of the vendored copy under ``tests/api/fixtures/``.
FIXTURE_NAME: Final[str] = "nest_source"

#: The single module that registers the whole nest-api surface.
_APP_MODULE: Final[str] = "apps/api/app.py"

#: Where the request handlers live, relative to a Nest checkout.
_HANDLERS_DIR: Final[str] = "apps/api/handlers"

#: Nest's api app carries **27 ``@app.route`` registrations across 21 distinct
#: paths** — six paths are registered twice, once per method (a collection's
#: GET and POST, an item's GET and DELETE). Both numbers are true and they get
#: quoted interchangeably, so both are pinned here and the distinction is
#: named wherever either is cited.
#:
#: The floors sit just under each so retiring one route does not fail the
#: parse, while a parser that stopped understanding the file's shape — and
#: would make every assertion built on this table vacuous — does.
_MINIMUM_REGISTRATIONS: Final[int] = 25
_MINIMUM_PATHS: Final[int] = 19


def _resolve_root(root: Path | None) -> Path:
    """Resolve the Nest checkout root, honouring the override.

    ``Path("")`` is ``PosixPath(".")`` and is truthy, so an unset variable is
    tested as a string before it ever becomes a ``Path``.
    """
    if root is not None:
        return root
    configured = os.environ.get(NEST_ROOT_ENV_VAR, "").strip()
    return Path(configured) if configured else DEFAULT_NEST_ROOT


def nest_api_module(root: Path | None = None) -> Path | None:
    """Return Nest's api app module, or None when no checkout is present."""
    module = _resolve_root(root) / _APP_MODULE
    return module if module.is_file() else None


def nest_handlers_dir(root: Path | None = None) -> Path | None:
    """Return Nest's handlers package, or None when no checkout is present."""
    handlers = _resolve_root(root) / _HANDLERS_DIR
    return handlers if handlers.is_dir() else None


def missing_reason(root: Path | None = None) -> str:
    """Explain a skip, naming what was looked for and how to redirect it."""
    return (
        f"nest source not available at {_resolve_root(root) / _APP_MODULE} — "
        f"this check needs Nest itself on disk and cannot run from the "
        f"vendored fixture. Set ${NEST_ROOT_ENV_VAR} to a checkout to run it, "
        f"or REQUIRE_PRODUCT_SOURCE=1 to make its absence a failure."
    )


def _string_literal(node: ast.expr | None) -> str | None:
    """Return a literal string node's value, or None for anything else."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _declared_methods(call: ast.Call) -> frozenset[str]:
    """Read the ``methods=[...]`` keyword, defaulting to GET as Quart does."""
    for keyword in call.keywords:
        if keyword.arg != "methods":
            continue
        if not isinstance(keyword.value, ast.List | ast.Tuple):
            continue
        methods = {
            literal.upper()
            for element in keyword.value.elts
            if (literal := _string_literal(element)) is not None
        }
        if methods:
            return frozenset(methods)
    return frozenset({"GET"})


def route_table(root: Path | None = None) -> dict[str, frozenset[str]]:
    """Return ``{registered_path: {methods}}`` from Nest's api app module.

    Paths are returned exactly as registered, Werkzeug converter syntax and
    all (``/api/v1/tenants/<tenant_id>/data-resources``), because the
    converter shape is part of what a caller has to match.

    Raises:
        FileNotFoundError: when no Nest checkout is present — callers should
            check :func:`nest_api_module` first and skip.
        AssertionError: when the parse under-reads, which would otherwise
            make every assertion built on this table pass vacuously.
    """
    module = nest_api_module(root)
    if module is None:
        raise FileNotFoundError(missing_reason(root))

    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    table: dict[str, set[str]] = {}
    registrations = 0

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            # Only `<something>.route(...)` decorators.
            if not isinstance(func, ast.Attribute) or func.attr != "route":
                continue
            if not decorator.args:
                continue
            path = _string_literal(decorator.args[0])
            if path is None:
                continue
            registrations += 1
            table.setdefault(path, set()).update(_declared_methods(decorator))

    assert registrations >= _MINIMUM_REGISTRATIONS and len(table) >= _MINIMUM_PATHS, (
        f"parsed {registrations} route registrations across {len(table)} "
        f"distinct paths from {module}, expected at least "
        f"{_MINIMUM_REGISTRATIONS} / {_MINIMUM_PATHS}. The file's registration "
        f"style has changed and this parser is under-reading — every check "
        f"built on it would pass vacuously until this is fixed."
    )

    return {path: frozenset(methods) for path, methods in table.items()}


def _envelope_key_of(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """Find the collection envelope key one list handler emits.

    Nest's list handlers all end in ``jsonify({<key>: [...], "meta": {"count":
    ..., "version": ...}})``. The ``meta``-with-``count`` sibling is what
    identifies the *collection* answer specifically — a handler also emits
    error dicts (``code``/``message``/``requestId``) and, for a single
    resource, a bare object. Keyed on that marker rather than on position, so
    reordering the returns does not change the answer.

    Returns ``None`` when the function has no such return, which is how a
    non-list handler is distinguished from one whose shape stopped being
    recognisable.
    """
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Dict):
            continue
        keys = [_string_literal(key) for key in inner.keys]
        if "meta" not in keys:
            continue
        meta = inner.values[keys.index("meta")]
        if not isinstance(meta, ast.Dict):
            continue
        if "count" not in [_string_literal(key) for key in meta.keys]:
            continue
        others = [key for key in keys if key is not None and key != "meta"]
        if len(others) == 1:
            return others[0]
    return None


def envelope_keys(root: Path | None = None) -> dict[str, str]:
    """Return ``{handler function name: collection envelope key}``.

    Nest has **no shared collection envelope** — only ``list_data_resources``
    answers ``items``; the others name ``snapshots``, ``policies`` and
    ``searchPools``. The portal decoded all four as ``items`` and fell back to
    an empty list, so three kinds rendered as permanently empty with no error
    anywhere. This is the derivation that binds the portal's per-kind table to
    Nest's own handlers rather than to a comment.

    Raises:
        FileNotFoundError: when no Nest checkout is present.
    """
    handlers = nest_handlers_dir(root)
    if handlers is None:
        raise FileNotFoundError(missing_reason(root))

    found: dict[str, str] = {}
    for path in sorted(handlers.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            key = _envelope_key_of(node)
            if key is not None:
                found[node.name] = key

    assert found, (
        f"parsed no collection envelopes from {handlers} — the handlers' "
        f"jsonify shape has changed and this parser is under-reading, which "
        f"would make the per-kind envelope check vacuous."
    )
    return found


def build_fixture(root: Path | None = None) -> dict[str, Any]:
    """Assemble the vendored payload from a live checkout."""
    table = route_table(root)
    return {
        **provenance(_resolve_root(root)),
        "_comment": (
            "Generated by `make refresh-product-source-fixtures` from a Nest "
            "checkout. Do not hand-edit: test_nest_source_fixture.py compares "
            "this against a live parse wherever a checkout exists. "
            "`path_count` is DISTINCT paths; Nest declares more @app.route "
            "registrations than that, since six paths carry two methods each."
        ),
        "path_count": len(table),
        "routes": unmethod_map(table),
        "envelope_keys": envelope_keys(root),
    }


def refresh_fixture(root: Path | None = None) -> Path:
    """Regenerate the vendored copy from a checkout."""
    return write_fixture(FIXTURE_NAME, build_fixture(root))


def vendored_route_table() -> dict[str, frozenset[str]]:
    """Nest's route table as vendored into this repo."""
    return method_map(load_fixture(FIXTURE_NAME)["routes"])


def vendored_envelope_keys() -> dict[str, str]:
    """Nest's per-handler collection envelope keys, as vendored."""
    raw = load_fixture(FIXTURE_NAME)["envelope_keys"]
    return {str(name): str(key) for name, key in raw.items()}


def effective_route_table(root: Path | None = None) -> dict[str, frozenset[str]]:
    """Nest's routes from a checkout if there is one, else from the fixture.

    This is what callers should use: the guards built on it then run on every
    machine, instead of skipping everywhere but one laptop.
    """
    if nest_api_module(root) is None:
        return vendored_route_table()
    return route_table(root)


def effective_envelope_keys(root: Path | None = None) -> dict[str, str]:
    """Envelope keys from a checkout if there is one, else from the fixture."""
    if nest_handlers_dir(root) is None:
        return vendored_envelope_keys()
    return envelope_keys(root)
