"""Parse Gough's real route registrations straight out of its source tree.

``FakeGough`` (``tests/api/test_gough_adapter.py``) routes every request
through a real :class:`werkzeug.routing.Map` built from
``_GOUGH_REAL_ROUTES`` — a **hand transcription** of Gough's route table. That
transcription is what makes the fake reproduce Gough's 308/404 slash
asymmetry, and it is also the fake's single point of failure: nothing detects
Gough renaming a route, dropping one, or flipping a trailing slash. The suite
would stay green while the adapter talked to endpoints that no longer exist.

This module closes that gap by deriving the same table from Gough's own
source, so ``test_gough_route_drift.py`` can assert the two agree.

Why an AST parse rather than importing Gough
============================================
Importing Gough's app package would be the most faithful reading, but it needs
Gough's full dependency set (``quart``, ``penguin-dal``, ``penguin-aaa``,
``aetcd``, ``hvac`` …) installed in the *portal's* interpreter, which is not a
dependency the portal has or should take. :mod:`ast` needs only the files on
disk, so the check runs anywhere a Gough checkout exists and skips cleanly
where one does not.

The cost is that the join semantics have to be reproduced rather than
observed, so they are pinned to Quart's own implementation and cited:

* ``BlueprintSetupState.__init__`` — ``url_prefix = options.get("url_prefix")``
  falling back to ``blueprint.url_prefix``. A prefix passed to
  ``register_blueprint`` **overrides** the constructor's, it does not
  concatenate. Gough relies on this: ``agents_bp`` declares
  ``url_prefix="/api/v1/agents"`` *and* is registered with the same prefix.
* ``BlueprintSetupState.add_url_rule`` —
  ``"/".join((url_prefix.rstrip("/"), rule.lstrip("/")))``. This is what
  preserves the trailing-slash distinction that matters here:
  ``route("/")`` under ``/api/v1/nodes`` yields ``/api/v1/nodes/`` (join with
  an empty right side leaves the separator), while ``route("/groups")``
  yields ``/api/v1/biomes/groups`` with no trailing slash.

Reproducing that by string concatenation instead would erase the exact
distinction the drift test exists to police, so the reproduction was verified
rather than assumed: on 2026-08-08 this parser's output was diffed against
``app.url_map`` of a **running** Gough (started from its own docker-compose)
and matched exactly — 154 routes on both sides, identical declared-method sets,
zero differences in either direction. The join semantics below are therefore
observed behaviour, not an approximation of it. Re-run that comparison (see
``README-gough-fixtures.md``) if this parser is ever changed.

Only *declared* methods are recorded. Werkzeug adds ``HEAD`` and ``OPTIONS``
to the url_map automatically; they are not part of what a handler declares and
are excluded on both sides of the comparison.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any, Final

from product_source_fixtures import (
    load_fixture,
    method_map,
    unmethod_map,
    write_fixture,
)

__all__ = [
    "DEFAULT_GOUGH_ROOT",
    "GOUGH_ROOT_ENV_VAR",
    "FIXTURE_NAME",
    "IMPLICIT_METHODS",
    "gough_app_root",
    "gough_source_routes",
    "vendored_gough_routes",
    "effective_gough_routes",
    "build_fixture",
    "refresh_fixture",
    "missing_reason",
]

#: Where a developer checkout of Gough normally lives. CI runners do not have
#: one, which is why every caller must handle ``None`` (see
#: :func:`missing_reason`).
DEFAULT_GOUGH_ROOT: Final[Path] = Path("/home/penguin/code/gough")

#: Override for a checkout in a different place (a CI job that clones Gough,
#: a developer who keeps it elsewhere).
GOUGH_ROOT_ENV_VAR: Final[str] = "GOUGH_SOURCE_ROOT"

#: Stem of the vendored copy under ``tests/api/fixtures/``. Nothing set
#: ``$GOUGH_SOURCE_ROOT`` anywhere in this repo, so the drift check skipped on
#: every machine without a checkout at the hardcoded default — see
#: :mod:`tests.api.product_source_fixtures`.
FIXTURE_NAME: Final[str] = "gough_source"

#: Methods Werkzeug synthesises. Never declared in a handler, so they are
#: excluded rather than expected.
IMPLICIT_METHODS: Final[frozenset[str]] = frozenset({"HEAD", "OPTIONS"})

#: The api-manager package, relative to a Gough checkout root.
_APP_PACKAGE: Final[str] = "services/api-manager/app"

#: Files carrying route registrations. ``api/*.py`` holds most of them, but
#: three route families the adapter depends on live outside it and would be
#: invisible to an ``api/*.py``-only parse:
#:
#: * ``__init__.py`` — the app-level ``/healthz``, ``/readyz`` and ``/metrics``
#:   routes, *and* every ``register_blueprint`` call, which is where a
#:   blueprint's effective prefix is decided;
#: * ``auth/__init__.py`` — ``/api/v1/auth/login`` and ``/refresh``, the two
#:   routes the adapter's session layer cannot work without;
#: * ``hello.py`` — ``/api/v1/status``.
_EXTRA_ROUTE_MODULES: Final[tuple[str, ...]] = (
    "__init__.py",
    "auth/__init__.py",
    "hello.py",
    "users.py",
)


def _resolve_root(root: Path | None) -> Path:
    """Pick the Gough checkout to read: explicit arg, then env, then default.

    ``Path("")`` is ``PosixPath(".")`` and is truthy, so an unset environment
    variable cannot be collapsed into the default with ``or`` — that reads the
    *current working directory* as a Gough checkout and reports "not found"
    with a relative path that names nothing. The empty string is therefore
    tested before it ever becomes a ``Path``.
    """
    if root is not None:
        return root
    configured = os.environ.get(GOUGH_ROOT_ENV_VAR, "").strip()
    return Path(configured) if configured else DEFAULT_GOUGH_ROOT


def gough_app_root(root: Path | None = None) -> Path | None:
    """Locate Gough's ``api-manager/app`` package, or ``None`` if absent.

    Returning ``None`` rather than raising is deliberate: "no Gough checkout"
    is the normal state on a CI runner and must produce a skip, while a
    checkout that exists but has moved its app package is a real failure the
    caller should see.
    """
    app_root = _resolve_root(root) / _APP_PACKAGE
    return app_root if app_root.is_dir() else None


def missing_reason(root: Path | None = None) -> str:
    """Explain, concretely, why the drift check cannot run.

    A bare ``skip`` with no reason is indistinguishable from a check that
    silently stopped covering anything, so the message names the path looked
    at and the environment variable that redirects it.
    """
    return (
        f"gough source not available at {_resolve_root(root) / _APP_PACKAGE} — "
        f"this check needs Gough itself on disk and cannot run from the "
        f"vendored fixture. Set ${GOUGH_ROOT_ENV_VAR} to a checkout to run it, "
        f"or REQUIRE_PRODUCT_SOURCE=1 to make its absence a failure."
    )


def _string_literal(node: ast.expr | None) -> str | None:
    """Return a ``str`` constant's value, or ``None`` for anything dynamic."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    """Find a keyword argument by name."""
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _blueprint_prefixes(tree: ast.AST) -> dict[str, str | None]:
    """Map ``<var> = Blueprint(..., url_prefix=...)`` to its constructor prefix.

    A blueprint with no ``url_prefix`` maps to ``None``, which is distinct
    from "not a blueprint" — the registration site may supply one.
    """
    prefixes: dict[str, str | None] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name != "Blueprint":
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                prefixes[target.id] = _string_literal(
                    _keyword(node.value, "url_prefix")
                )
    return prefixes


def _registrations(tree: ast.AST) -> dict[str, str | None]:
    """Map a blueprint variable to the ``url_prefix`` it was registered with.

    Presence in this mapping means "registered"; the value is the override or
    ``None`` when ``register_blueprint`` passed no prefix (in which case the
    constructor's applies).
    """
    registered: dict[str, str | None] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "register_blueprint":
            continue
        if not node.args or not isinstance(node.args[0], ast.Name):
            continue
        registered[node.args[0].id] = _string_literal(_keyword(node, "url_prefix"))
    return registered


def _declared_methods(call: ast.Call) -> frozenset[str]:
    """Methods a ``route()`` decorator declares.

    Werkzeug defaults an omitted ``methods`` to ``GET``; that default is part
    of the route's real behaviour, so it is materialised here rather than left
    as an empty set that would compare equal to nothing.
    """
    methods_node = _keyword(call, "methods")
    if methods_node is None:
        return frozenset({"GET"})
    if not isinstance(methods_node, (ast.List, ast.Tuple, ast.Set)):
        return frozenset()
    values = {
        literal.upper()
        for element in methods_node.elts
        if (literal := _string_literal(element)) is not None
    }
    return frozenset(values - IMPLICIT_METHODS)


def _route_decorators(tree: ast.AST) -> list[tuple[str, str, frozenset[str]]]:
    """Collect ``@<target>.route("<rule>", methods=[...])`` declarations.

    ``target`` is the decorated object's variable name — a blueprint
    (``nodes_bp``) or the app itself (``app``). Both matter: ``/healthz`` and
    ``/metrics`` are registered directly on ``app``.

    Both ``FunctionDef`` and ``AsyncFunctionDef`` are walked; Gough's handlers
    are ``async def`` and a parser that only looked at ``FunctionDef`` would
    silently find no routes at all.
    """
    found: list[tuple[str, str, frozenset[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not isinstance(func, ast.Attribute) or func.attr != "route":
                continue
            if not isinstance(func.value, ast.Name):
                continue
            if not decorator.args:
                continue
            rule = _string_literal(decorator.args[0])
            if rule is None:
                continue
            found.append((func.value.id, rule, _declared_methods(decorator)))
    return found


def _join(prefix: str | None, rule: str) -> str:
    """Join a blueprint prefix and a rule the way Quart does.

    Mirrors ``BlueprintSetupState.add_url_rule``. The empty-``rule`` branch is
    unreachable from a ``route()`` decorator (an empty path is not written)
    but is kept so this function is a faithful statement of the semantics
    rather than a convenient subset of them.
    """
    if prefix is None:
        return rule
    if not rule:
        return prefix
    return "/".join((prefix.rstrip("/"), rule.lstrip("/")))


def _route_module_paths(app_root: Path) -> list[Path]:
    """Every source file that can register a route, deduplicated and ordered."""
    paths: list[Path] = sorted((app_root / "api").glob("*.py"))
    paths.extend(
        candidate
        for name in _EXTRA_ROUTE_MODULES
        if (candidate := app_root / name).is_file()
    )
    return paths


def gough_source_routes(root: Path | None = None) -> dict[str, frozenset[str]]:
    """Parse Gough's registered routes into ``{path: declared methods}``.

    Methods are unioned per path, because Gough splits verbs across separate
    decorators (``/nodes/<int:node_id>`` is declared three times, for GET,
    PATCH and DELETE).

    A blueprint that is never registered contributes nothing: its rules exist
    in source but the app does not serve them, and reporting them would make
    the drift test demand routes Gough answers 404 for.

    Raises ``FileNotFoundError`` when no Gough checkout is present — callers
    that should skip instead must check :func:`gough_app_root` first.
    """
    app_root = gough_app_root(root)
    if app_root is None:
        raise FileNotFoundError(missing_reason(root))

    module_trees: list[ast.AST] = []
    for path in _route_module_paths(app_root):
        module_trees.append(
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        )

    constructor_prefixes: dict[str, str | None] = {}
    registrations: dict[str, str | None] = {}
    decorators: list[tuple[str, str, frozenset[str]]] = []
    for tree in module_trees:
        constructor_prefixes.update(_blueprint_prefixes(tree))
        registrations.update(_registrations(tree))
        decorators.extend(_route_decorators(tree))

    routes: dict[str, set[str]] = {}
    for target, rule, methods in decorators:
        if target in constructor_prefixes:
            if target not in registrations:
                # Declared but never registered — the app does not serve it.
                continue
            override = registrations[target]
            prefix = override if override is not None else constructor_prefixes[target]
        else:
            # Registered directly on the app object (``@app.route(...)``):
            # no prefix applies.
            prefix = None
        routes.setdefault(_join(prefix, rule), set()).update(methods)

    return {path: frozenset(methods) for path, methods in routes.items()}


def build_fixture(root: Path | None = None) -> dict[str, Any]:
    """Assemble the vendored payload from a live Gough checkout."""
    table = gough_source_routes(root)
    return {
        "_comment": (
            "Generated by `make refresh-product-source-fixtures` from a Gough "
            "checkout. Do not hand-edit: test_gough_route_drift.py compares "
            "this against a live parse wherever a checkout exists."
        ),
        "path_count": len(table),
        "routes": unmethod_map(table),
    }


def refresh_fixture(root: Path | None = None) -> Path:
    """Regenerate the vendored copy from a checkout."""
    return write_fixture(FIXTURE_NAME, build_fixture(root))


def vendored_gough_routes() -> dict[str, frozenset[str]]:
    """Gough's route table as vendored into this repo."""
    return method_map(load_fixture(FIXTURE_NAME)["routes"])


def effective_gough_routes(root: Path | None = None) -> dict[str, frozenset[str]]:
    """Gough's routes from a checkout if there is one, else from the fixture.

    Callers should use this rather than :func:`gough_source_routes` directly:
    the drift check then runs everywhere instead of skipping wherever no
    checkout sits at the hardcoded default.
    """
    if gough_app_root(root) is None:
        return vendored_gough_routes()
    return gough_source_routes(root)
