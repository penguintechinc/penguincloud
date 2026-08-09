"""Derive Tobogganing's real route table — and its per-route auth mechanism.

Same purpose as :mod:`tests.api.gough_route_source` and
:mod:`tests.api.nest_route_source`: grade the portal's allowlist and adapter
against the product's own registrations rather than against a transcription.

Why a live boot rather than an AST parse
========================================
Nest is parsed with :mod:`ast` because ``apps/api/app.py`` registers every
route with a bare ``@app.route("/final/path")`` — the decorator's first
argument IS the final path, so a parse of one file is exact.

Tobogganing is not like that, and an AST parse would be **wrong**, not merely
awkward. Its final paths are assembled at runtime by a module registry:

    final path = "/api/v1/" + module_name + blueprint.url_prefix + route_rule
                 (hub_api/registry/registry.py:58-62)

The three parts live in three different files, and one of them (``module_name``)
is not written next to the route at all — it comes from the ``ModuleContract``
the module's ``module()`` factory returns. Worse, the registry mounts blueprints
inside ``before_serving``, so even importing the app is not enough; Tobogganing's
own spec generator says so in a comment (``scripts/generate_openapi.py:72-78``:
"a plain app_context() does NOT run before_serving, so the spec would contain
only the core routes and miss every module").

So the derivation boots the app the way the product's own tooling does
(``create_app()`` inside ``async with app.test_app()``) and reads
``app.url_map``. That is the registration table itself — no joining rules to
get wrong, and trailing slashes are preserved exactly as Werkzeug holds them.

Why a subprocess
================
The boot is run in a child interpreter, not imported into the portal's pytest
process. Tobogganing ships top-level packages (``hub_api``, ``shared``, ``libs``)
that would collide with the portal's own import namespace, it mutates global
state (``set_encryptor``), and a missing product dependency should degrade to
"use the vendored fixture" rather than take down collection of the whole suite.

What is captured, and why auth is part of it
============================================
Alongside ``{path: {methods}}`` this records, per route, **which auth mechanism
guards it**. That is not decoration — it is the fact that decides whether a
route can back a portal screen at all:

``require_machine_jwt`` rejects any token whose ``aud`` is not ``"headend"``
(``hub_api/auth/middleware.py:516-517``), and the credential a portal connection
stores comes from ``POST /api/v1/auth/login``, which issues ``aud =
config.product_name`` = ``"tobogganing"`` (``hub_api/auth/service.py:341``,
``hub_api/config/__init__.py:36``). Eight routes are machine-only for that
reason — including ``/firewall/rules``, ``/wireguard/peers`` and
``/headend/<id>/ports``, all three of which Task 4T's brief named as portal
resources.

Capturing it here means ``test_tobogganing_allowlist.py`` can assert *from the
product's source* that no allowlist rule points at a route the portal's
credential can never satisfy, instead of that claim living in a comment which
goes stale the first time Tobogganing changes a decorator.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
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
    "DEFAULT_TOBOGGANING_ROOT",
    "TOBOGGANING_ROOT_ENV_VAR",
    "FIXTURE_NAME",
    "AUTH_MACHINE_JWT",
    "AUTH_USER_JWT",
    "AUTH_NODE_CREDENTIAL",
    "MACHINE_JWT_AUDIENCE",
    "tobogganing_app_module",
    "missing_reason",
    "boot_failure",
    "route_table",
    "auth_table",
    "vendored_route_table",
    "vendored_auth_table",
    "effective_route_table",
    "effective_auth_table",
    "machine_only_paths",
    "build_fixture",
    "refresh_fixture",
]

#: Where a Tobogganing checkout normally lives on a PenguinTech dev machine.
DEFAULT_TOBOGGANING_ROOT: Final[Path] = Path("/home/penguin/code/tobogganing")

#: Override for a checkout somewhere else.
TOBOGGANING_ROOT_ENV_VAR: Final[str] = "TOBOGGANING_SOURCE_ROOT"

#: Stem of the vendored copy under ``tests/api/fixtures/``.
FIXTURE_NAME: Final[str] = "tobogganing_source"

#: The app factory module, used only to decide whether a checkout is present.
_APP_MODULE: Final[str] = "hub_api/app.py"

#: Auth classifications recorded per route.
#:
#: ``machine`` — ``@require_machine_jwt``. Demands ``aud == "headend"``, which
#: no portal login token carries. Unreachable with a stored user credential.
#: ``user`` — ``@require_tenant`` and/or ``@require_scope``. This is the only
#: class a portal connection can exercise.
#: ``node`` — no decorator, but the handler authenticates a node credential
#: inline (bootstrap enrolment token or a client api_key). Also unreachable,
#: and several of these MINT credentials, so they matter to the allowlist.
#: ``none`` — genuinely unauthenticated.
AUTH_MACHINE_JWT: Final[str] = "machine"
AUTH_USER_JWT: Final[str] = "user"
AUTH_NODE_CREDENTIAL: Final[str] = "node"
AUTH_NONE: Final[str] = "none"

#: The audience a machine-JWT must carry. A portal login token cannot have it.
MACHINE_JWT_AUDIENCE: Final[str] = "headend"

#: Floors under the observed counts. Tobogganing boots **139 rules across 9
#: modules**; the floors sit well below so retiring a route does not fail the
#: derivation, while a boot that silently mounted no modules — which would make
#: every check built on this table vacuous — does.
_MINIMUM_RULES: Final[int] = 120
_MINIMUM_MACHINE_ROUTES: Final[int] = 6

#: How long the child interpreter gets to boot the product.
_BOOT_TIMEOUT_SECONDS: Final[int] = 180

#: Decorator names treated as user-JWT auth.
_USER_DECORATORS: Final[frozenset[str]] = frozenset(
    {
        "require_tenant",
        "require_scope",
        "require_session_user",
        "require_role",
        "require_permission",
    }
)

#: Handler-body markers for inline node-credential auth. These handlers carry no
#: decorator, so a decorator scan alone would misreport them as public — and two
#: of them (``POST /sdwan/clients``, ``POST /sdwan/clusters``) return a freshly
#: minted ``api_key`` in the response body.
_NODE_AUTH_MARKERS: Final[tuple[str, ...]] = (
    "_verify_bootstrap_token",
    "authenticate_client",
    "authenticate_cluster",
    "_verify_headend_token",
)

# The program run in the child interpreter. Kept as source text rather than a
# file on disk so there is nothing to leave behind, and nothing another
# concurrently-running agent could collide with.
_BOOT_PROGRAM: Final[str] = r'''
import asyncio, inspect, json, sys

USER_DECORATORS = %(user_decorators)r
NODE_MARKERS = %(node_markers)r
MACHINE_DECORATOR = "require_machine_jwt"


def classify(view):
    """Classify one view function's auth mechanism from its own source."""
    inner, seen = view, set()
    while hasattr(inner, "__wrapped__") and id(inner) not in seen:
        seen.add(id(inner))
        inner = inner.__wrapped__
    try:
        lines, _ = inspect.getsourcelines(inner)
    except (OSError, TypeError):
        return "unknown", []
    decorators, body_started = [], False
    for line in lines:
        s = line.strip()
        if s.startswith("@"):
            if not body_started:
                decorators.append(s.lstrip("@"))
            continue
        if s.startswith("def ") or s.startswith("async def "):
            body_started = True
    names = {d.split("(")[0] for d in decorators}
    if MACHINE_DECORATOR in names:
        return "machine", decorators
    if names & set(USER_DECORATORS):
        return "user", decorators
    body = "".join(lines)
    if any(marker in body for marker in NODE_MARKERS):
        return "node", decorators
    return "none", decorators


async def main():
    from hub_api.app import create_app

    app = create_app()
    async with app.test_app():
        out = []
        for rule in app.url_map.iter_rules():
            methods = sorted(
                m for m in (rule.methods or set()) if m not in ("HEAD", "OPTIONS")
            )
            view = app.view_functions.get(rule.endpoint)
            kind, decorators = classify(view) if view else ("unknown", [])
            out.append({
                "rule": str(rule.rule),
                "methods": methods,
                "endpoint": rule.endpoint,
                "auth": kind,
                "decorators": decorators,
                "strict_slashes": bool(rule.strict_slashes),
            })
    json.dump(out, sys.stdout)
    return 0


sys.exit(asyncio.run(main()))
''' % {
    "user_decorators": sorted(_USER_DECORATORS),
    "node_markers": list(_NODE_AUTH_MARKERS),
}


def _resolve_root(root: Path | None) -> Path:
    """Resolve the Tobogganing checkout root, honouring the override.

    ``Path("")`` is ``PosixPath(".")`` and is truthy, so an unset variable is
    tested as a string before it ever becomes a ``Path``.
    """
    if root is not None:
        return root
    configured = os.environ.get(TOBOGGANING_ROOT_ENV_VAR, "").strip()
    return Path(configured) if configured else DEFAULT_TOBOGGANING_ROOT


def tobogganing_app_module(root: Path | None = None) -> Path | None:
    """Return Tobogganing's app factory module, or None when absent."""
    module = _resolve_root(root) / _APP_MODULE
    return module if module.is_file() else None


def missing_reason(root: Path | None = None) -> str:
    """Explain a skip, naming what was looked for and how to redirect it."""
    return (
        f"tobogganing source not available at "
        f"{_resolve_root(root) / _APP_MODULE} — this check needs Tobogganing "
        f"itself on disk (and its dependencies importable) and cannot run from "
        f"the vendored fixture. Set ${TOBOGGANING_ROOT_ENV_VAR} to a checkout "
        f"to run it, or REQUIRE_PRODUCT_SOURCE=1 to make its absence a failure."
    )


class BootError(RuntimeError):
    """Tobogganing is on disk but would not boot."""


def _boot(root: Path | None = None) -> list[dict[str, Any]]:
    """Boot Tobogganing in a child interpreter and return its rule dump.

    Raises:
        FileNotFoundError: no checkout present.
        BootError: checkout present but the boot failed — distinct from
            "absent" so a broken product install is reported rather than
            silently falling back to a fixture that may disagree with it.
    """
    module = tobogganing_app_module(root)
    if module is None:
        raise FileNotFoundError(missing_reason(root))
    checkout = _resolve_root(root)

    env = dict(os.environ)
    # Keep the child's imports pointed at the product, not the portal.
    env["PYTHONPATH"] = str(checkout)
    try:
        result = subprocess.run(
            [sys.executable, "-c", _BOOT_PROGRAM],
            cwd=str(checkout),
            env=env,
            capture_output=True,
            text=True,
            timeout=_BOOT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BootError(f"could not run the Tobogganing boot: {exc}") from exc

    if result.returncode != 0:
        raise BootError(
            f"Tobogganing failed to boot (exit {result.returncode}). "
            f"stderr tail: {result.stderr.strip()[-2000:]}"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise BootError(
            f"Tobogganing boot produced no parseable rule dump: {exc}. "
            f"stdout head: {result.stdout[:500]!r}"
        ) from exc
    if not isinstance(payload, list):
        raise BootError("Tobogganing boot did not return a list of rules")
    return payload


def boot_failure(root: Path | None = None) -> str | None:
    """Return why a live boot is unavailable, or None when one would work.

    Lets a test say *which* of "no checkout" and "checkout will not boot"
    happened, instead of collapsing both into one skip message.
    """
    if tobogganing_app_module(root) is None:
        return missing_reason(root)
    try:
        _boot(root)
    except BootError as exc:
        return str(exc)
    return None


def _rules(root: Path | None = None) -> list[dict[str, Any]]:
    """Boot once and validate the dump is not vacuously short."""
    payload = _boot(root)
    machine = sum(1 for r in payload if r.get("auth") == AUTH_MACHINE_JWT)
    assert len(payload) >= _MINIMUM_RULES and machine >= _MINIMUM_MACHINE_ROUTES, (
        f"booted Tobogganing exposed {len(payload)} rules "
        f"({machine} machine-JWT), expected at least {_MINIMUM_RULES} / "
        f"{_MINIMUM_MACHINE_ROUTES}. The module registry did not mount — every "
        f"check built on this table would pass vacuously until this is fixed."
    )
    return payload


def route_table(root: Path | None = None) -> dict[str, frozenset[str]]:
    """Return ``{registered_path: {methods}}`` from a live Tobogganing boot.

    Paths come back exactly as registered, Werkzeug converter syntax and
    trailing slashes included (``/api/v1/clusters/`` really does carry one
    while ``/api/v1/sdwan/clusters`` does not) — the slash is part of what a
    caller has to match and no spec records it.
    """
    table: dict[str, set[str]] = {}
    for entry in _rules(root):
        table.setdefault(str(entry["rule"]), set()).update(
            str(m) for m in entry["methods"]
        )
    return {path: frozenset(methods) for path, methods in table.items()}


def auth_table(root: Path | None = None) -> dict[str, str]:
    """Return ``{"METHOD /path": auth_kind}`` from a live Tobogganing boot.

    Keyed by method as well as path because the two differ per verb on the
    same path in this product — ``GET /api/v1/sdwan/clients`` is user-JWT
    while ``POST /api/v1/sdwan/clients`` is an unauthenticated-decorator
    enrolment route that mints an api_key.
    """
    table: dict[str, str] = {}
    for entry in _rules(root):
        for method in entry["methods"]:
            table[f"{method} {entry['rule']}"] = str(entry["auth"])
    return table


def build_fixture(root: Path | None = None) -> dict[str, Any]:
    """Assemble the vendored payload from a live boot."""
    rules = _rules(root)
    table: dict[str, set[str]] = {}
    auth: dict[str, str] = {}
    for entry in rules:
        table.setdefault(str(entry["rule"]), set()).update(
            str(m) for m in entry["methods"]
        )
        for method in entry["methods"]:
            auth[f"{method} {entry['rule']}"] = str(entry["auth"])
    frozen = {path: frozenset(methods) for path, methods in table.items()}
    return {
        **provenance(_resolve_root(root)),
        "_comment": (
            "Generated by `make refresh-product-source-fixtures` from a "
            "Tobogganing checkout, by BOOTING the app (create_app() inside "
            "app.test_app()) and reading app.url_map — not by parsing source. "
            "Tobogganing assembles final paths at runtime in its module "
            "registry (/api/v1/{module} + blueprint.url_prefix + rule) and "
            "mounts module blueprints in before_serving, so no static parse is "
            "exact. Do not hand-edit: test_tobogganing_source_fixture.py "
            "compares this against a live boot wherever a checkout exists. "
            "`auth` records which credential class guards each route; "
            "'machine' routes demand aud=='headend' and are unreachable with "
            "the user token a portal connection stores."
        ),
        "path_count": len(frozen),
        "rule_count": len(rules),
        "routes": unmethod_map(frozen),
        "auth": auth,
    }


def refresh_fixture(root: Path | None = None) -> Path:
    """Regenerate the vendored copy from a checkout."""
    return write_fixture(FIXTURE_NAME, build_fixture(root))


def vendored_route_table() -> dict[str, frozenset[str]]:
    """Tobogganing's route table as vendored into this repo."""
    return method_map(load_fixture(FIXTURE_NAME)["routes"])


def vendored_auth_table() -> dict[str, str]:
    """Tobogganing's per-route auth classes, as vendored."""
    raw = load_fixture(FIXTURE_NAME)["auth"]
    return {str(key): str(value) for key, value in raw.items()}


def effective_route_table(root: Path | None = None) -> dict[str, frozenset[str]]:
    """Routes from a live boot if one is possible, else from the fixture.

    This is what callers should use: the guards built on it then run on every
    machine, instead of skipping everywhere but one laptop.
    """
    if tobogganing_app_module(root) is None:
        return vendored_route_table()
    try:
        return route_table(root)
    except BootError:
        return vendored_route_table()


def effective_auth_table(root: Path | None = None) -> dict[str, str]:
    """Auth classes from a live boot if one is possible, else from the fixture."""
    if tobogganing_app_module(root) is None:
        return vendored_auth_table()
    try:
        return auth_table(root)
    except BootError:
        return vendored_auth_table()


def machine_only_paths(root: Path | None = None) -> frozenset[str]:
    """``{"METHOD /path"}`` for every route a portal credential cannot reach.

    Both ``machine`` (``aud=="headend"``) and ``node`` (inline bootstrap token
    or client api_key) belong here: neither is satisfiable by the token
    ``POST /api/v1/auth/login`` issues, so an allowlist rule pointing at one is
    a guaranteed 401 dressed up as a feature.
    """
    return frozenset(
        key
        for key, kind in effective_auth_table(root).items()
        if kind in {AUTH_MACHINE_JWT, AUTH_NODE_CREDENTIAL}
    )
