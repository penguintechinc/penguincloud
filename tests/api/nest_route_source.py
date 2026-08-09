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
from typing import Final

__all__ = [
    "DEFAULT_NEST_ROOT",
    "NEST_ROOT_ENV_VAR",
    "nest_api_module",
    "missing_reason",
    "route_table",
]

#: Where a Nest checkout normally lives on a PenguinTech dev machine.
DEFAULT_NEST_ROOT: Final[Path] = Path("/home/penguin/code/nest")

#: Override for a checkout somewhere else.
NEST_ROOT_ENV_VAR: Final[str] = "NEST_SOURCE_ROOT"

#: The single module that registers the whole nest-api surface.
_APP_MODULE: Final[str] = "apps/api/app.py"

#: Registrations expected in that file. A parse returning fewer than this
#: means the file's shape changed and the parser is silently under-reading —
#: which would make every assertion built on it vacuous.
_MINIMUM_ROUTES: Final[int] = 20


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


def missing_reason(root: Path | None = None) -> str:
    """Explain a skip, naming what was looked for and how to redirect it."""
    return (
        f"nest source not available at {_resolve_root(root) / _APP_MODULE} — "
        f"this check reads Nest's route registrations off disk and is skipped "
        f"where no checkout exists (CI runners). Set ${NEST_ROOT_ENV_VAR} to a "
        f"checkout to run it."
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
        if not isinstance(keyword.value, (ast.List, ast.Tuple)):
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

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
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
            table.setdefault(path, set()).update(_declared_methods(decorator))

    assert len(table) >= _MINIMUM_ROUTES, (
        f"parsed only {len(table)} routes from {module}, expected at least "
        f"{_MINIMUM_ROUTES}. The file's registration style has changed and "
        f"this parser is under-reading — every check built on it would pass "
        f"vacuously until this is fixed."
    )

    return {path: frozenset(methods) for path, methods in table.items()}
