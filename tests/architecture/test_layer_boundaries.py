"""Mechanically enforce the portal-api layer dependency direction.

Phase 8, §11.2. OpenStack's failure mode was gradual cross-layer creep,
each step locally justified by whoever wrote it — nothing was ever
obviously wrong in isolation, only in aggregate. A guard that runs once and
is never revisited is exactly as vulnerable to that as no guard at all, so
this module is built to avoid two specific ways a layering check quietly
stops meaning anything:

1. **A hand-maintained file list.** If "which files does this check" were a
   literal list, a new module added later is invisible to it by
   construction — the guard would keep passing while covering less and
   less of the tree. :func:`_discover_modules` globs ``app/**/*.py``
   instead, and :func:`_layer_of` raises rather than returning ``None`` for
   a module it cannot classify, so a new top-level file fails the very
   first time this test runs against it until someone deliberately places
   it in a layer.

2. **Only looking at top-level imports.** ``app/models.py`` imports
   ``app.devmode`` and ``app.quotas`` — a real, upward edge — but only
   inside function bodies (``from . import quotas`` a few lines before the
   call site), never at module scope. A checker that walked only
   ``ast.Module.body`` would report this file clean. :func:`_imports_in`
   walks the **entire** AST (``ast.walk``, not ``ast.iter_child_nodes`` on
   the module body), so a deferred import, a ``TYPE_CHECKING``-guarded one,
   or one inside a ``try/except ImportError`` fallback is exactly as
   visible as one at the top of the file.

What "layer" means here
========================
Bottom to top: **floor** → **auth** / **tenancy** (peers) → **licensing** /
**proxy** (peers) → **health** → **routes**. A module may import anything
in a *strictly lower* layer, and anything in its *own* layer (including a
peer module in the same named layer, e.g. ``app.proxy`` importing
``app.product_access``). It may **not** import a peer layer at the same
rank (``app.auth`` importing ``app.tenancy`` — both rank 1, different
layers) or anything above it (``app.health`` importing ``app.products`` —
routes is rank 4, health is rank 3). See :data:`LAYER_OF` and
:data:`_RANK` for the exact membership and ranking, and
``docs/APP_STANDARDS.md``-adjacent context in the Phase 8 audit for why
this order is the healthy one.

``app/__init__.py`` (the Quart application factory) is deliberately
excluded as a *source* — it is the composition root, wired to import from
every layer by design, and auditing it would just be re-stating that a
dependency-injection root exists.

The exception list
===================
:data:`ALLOWED_EXCEPTIONS` is a grandfather list, not a permission slip —
each entry names the one real edge it covers and why. It is checked in
**both directions**: a real violation missing from the list fails the test
(the guard actually gates), and a list entry that no longer corresponds to
a real violation *also* fails it (see
:func:`test_exception_list_has_no_stale_entries`), so the list cannot grow
stale opt-outs nobody has looked at since. Section C of the accompanying
work proves the first direction by deliberately introducing a sideways
import, watching this file fail, then reverting it.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

#: Root of the audited package, resolved from this file's own path so the
#: test does not depend on the pytest invocation's cwd.
_APP_ROOT: Final[Path] = Path(__file__).resolve().parents[2] / "services" / "portal-api" / "app"

#: Layer name -> rank, bottom (0) to top (4). Two layer NAMES may share a
#: rank (auth/tenancy at 1, licensing/proxy at 2) -- they are peers, and an
#: import between peers is sideways, not downward, even though the numbers
#: are equal.
_RANK: Final[dict[str, int]] = {
    "floor": 0,
    "auth": 1,
    "tenancy": 1,
    "licensing": 2,
    "proxy": 2,
    "health": 3,
    "routes": 4,
}

#: Every module directly under ``app/`` (its dotted path's second segment,
#: e.g. ``app.tenancy.authz`` classifies as ``tenancy``; ``app.adapters.gough
#: .adapter`` classifies as ``adapters`` -> ``proxy``), mapped to its layer.
#: Deliberately explicit rather than a fallback/default bucket: an
#: unrecognised component is a bug in THIS table, not a module the guard is
#: entitled to skip -- see :func:`_layer_of`.
LAYER_OF: Final[dict[str, str]] = {
    # floor -- models.py/DAL, encryption.py, config.py, killkrill.py,
    # ratelimit.py, plus the two Phase 8 relocations (rbac.py,
    # adapter_errors.py) that exist specifically so this layer stays free
    # of any adapters/tenancy/licensing dependency.
    "models": "floor",
    "models_sqlalchemy": "floor",
    "encryption": "floor",
    "config": "floor",
    "killkrill": "floor",
    "killkrill_client": "floor",
    "ratelimit": "floor",
    "rbac": "floor",
    "adapter_errors": "floor",
    # audit_view.py was not named in the Phase 8 audit's floor list, but
    # this guard's own scan is the tiebreaker: it has zero app-internal
    # imports of its own (verified -- `grep '^from \.' app/audit_view.py`
    # returns nothing) and is a self-contained security-scoping DTO (which
    # audit columns are safe to publish, per security.md's Output
    # Validation), the same shape as PII tokenization -- not a blueprint
    # (no `Blueprint` object, no `@_bp.route`). Classifying it under
    # "routes" because it happens to live next to audit.py made
    # app.auth_features's real (top-level) import of it read as auth
    # reaching four layers up into route handlers, when the dependency is
    # actually floor-level and one-directional every place it is used
    # (audit.py, auth_features.py, dashboard_api.py, product_view.py).
    "audit_view": "floor",
    # auth
    "middleware": "auth",
    "authz": "auth",
    "auth": "auth",
    "auth_features": "auth",
    "mfa": "auth",
    # tenancy
    "tenancy": "tenancy",
    # licensing
    "licensing": "licensing",
    "license": "licensing",
    "flags": "licensing",
    "devmode": "licensing",
    "quotas": "licensing",
    # proxy
    "proxy": "proxy",
    "product_access": "proxy",
    "adapters": "proxy",
    # health
    "health_api": "health",
    "health_cache": "health",
    "health_poller": "health",
    "background": "health",
    # routes (blueprints, and API-surface modules with no downstream
    # importer inside app/ -- the top layer, so a wrong guess here can
    # only ever be too permissive about THIS module as a source, never
    # hide an edge INTO a lower layer, which is what actually matters).
    "dashboard_api": "routes",
    "features_api": "routes",
    "license_api": "routes",
    "operations_api": "routes",
    "products": "routes",
    "product_view": "routes",
    "resources_api": "routes",
    "teams": "routes",
    "tenants": "routes",
    "users": "routes",
    "audit": "routes",
    "oauth": "routes",
    "discovery": "routes",
    "hello": "routes",
    "openapi": "routes",
    "grpc": "routes",
}


def _module_name(path: Path) -> str:
    """Dotted module name for a file under :data:`_APP_ROOT`, e.g. ``app.tenancy.authz``."""
    rel = path.relative_to(_APP_ROOT.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _component(dotted: str) -> str | None:
    """The layer-classifiable piece of a dotted ``app.…`` module name.

    ``app.tenancy.authz`` -> ``"tenancy"``; ``app.adapters.gough.adapter``
    -> ``"adapters"``; bare ``"app"`` (the composition root, or a resolved
    relative import with no trailing name) -> ``None``, deliberately
    unclassified rather than misclassified, since ``app/__init__.py`` is
    excluded from this audit entirely.
    """
    if dotted == "app" or not dotted.startswith("app."):
        return None
    return dotted.split(".")[1]


def _layer_of(dotted: str) -> str:
    """Resolve a module to its layer name, or fail loudly.

    Raising rather than returning ``None`` for an unrecognised component is
    the point: see the module docstring's point (1). A module this table
    has never seen is a classification gap, not something safe to skip.
    """
    component = _component(dotted)
    if component is None or component not in LAYER_OF:
        raise AssertionError(
            f"unclassified app module for the layer guard: {dotted!r} "
            f"(component {component!r}) -- add it to LAYER_OF in "
            f"{__file__}, in the layer it actually belongs to."
        )
    return LAYER_OF[component]


def _resolve_relative(module: str | None, level: int, package: str) -> str | None:
    """Resolve a relative ``from`` import to an absolute dotted name.

    Mirrors ``importlib._bootstrap._resolve_name``: ``package`` is the
    importing module's own ``__package__`` (itself for a package
    ``__init__.py``, its parent otherwise). Returns ``None`` for a relative
    import that reaches past the top of the ``app`` package (malformed, or
    genuinely outside scope) rather than raising -- that is a syntax
    question for Python itself, not this guard's concern.
    """
    bits = package.rsplit(".", level - 1)
    if len(bits) < level:
        return None
    base = bits[0]
    return f"{base}.{module}" if module else base


def _imports_in(path: Path, own_module: str, is_package_init: bool) -> list[str]:
    """Every module this file imports from, anywhere in its AST.

    Walks the full tree (``ast.walk``), not just top-level statements, so a
    deferred import inside a function body -- the shape ``app/models.py``
    and ``app/auth.py`` both use for their real cross-layer edges -- is
    caught exactly like a module-scope one. Returns absolute dotted module
    names; callers filter to the ``app.*`` ones they care about.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    own_package = own_module if is_package_init else own_module.rsplit(".", 1)[0]

    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    targets.append(node.module)
                continue
            resolved = _resolve_relative(node.module, node.level, own_package)
            if resolved is None:
                continue
            if node.module:
                targets.append(resolved)
            else:
                # Bare `from . import x, y` -- each alias may itself be a
                # submodule of the resolved package.
                targets.extend(f"{resolved}.{alias.name}" for alias in node.names)
    return targets


def _discover_modules() -> list[Path]:
    """Every ``app/**/*.py`` file, excluding the composition root.

    Globbed, not hand-listed -- see the module docstring's point (1).
    """
    return sorted(p for p in _APP_ROOT.rglob("*.py") if p != _APP_ROOT / "__init__.py")


#: One entry per real, currently-existing sideways/upward edge this guard
#: allows. ``(source dotted module, target layer-component)``. Each is a
#: pre-existing edge from before this guard existed, verified against the
#: post-relocation tree (Phase 8 Part A removed the two worst ones --
#: app.authz -> app.adapters.base for RBACEnforcer, and the
#: routes/health -> app.adapters.base error-taxonomy imports -- so they are
#: NOT listed here), not a design endorsement. Each is scheduled for
#: cleanup, not sanctioned as correct.
#:
#: This list is LONGER than the three edges the Phase 8 audit named
#: (models->devmode/quotas, auth->licensing/devmode/quotas), and does not
#: include a fourth the audit named -- background.py -> app.license.
#: Verified rather than assumed, per the task brief: background.py is
#: "health" (rank 3) and app.license is "licensing" (rank 2), so that
#: import is already a healthy downward one and was never a violation --
#: this guard does not need to allow it, because it never flags it. The
#: five entries below were found by walking the FULL ast of every file
#: (module-scope and deferred imports alike -- the same technique that
#: surfaces models.py's and auth.py's edges, which only show up inside
#: function bodies) rather than assumed from the audit's summary; each was
#: individually confirmed against the source before being added here, and
#: the reverse edge (target importing back from source) was checked and
#: does not exist for any of them -- these are one-directional dependencies
#: that happen to run against the audit's stated peer grouping for
#: auth/tenancy and licensing/proxy, not accidental drift.
ALLOWED_EXCEPTIONS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        # app/models.py (floor) calls `from . import devmode` /
        # `from . import quotas` inside three functions
        # (create_tenant/create_team/add_tenant_admin's quota and
        # dev-mode-cap checks) to enforce registration limits at the DAL
        # layer -- the deliberate backstop the task brief names as "the
        # seed to watch": floor reaching into licensing decision logic.
        # Both are deferred imports (avoids a real circular import at
        # module load time, since devmode/quotas import app.models back),
        # visible to this guard only because it walks the full AST rather
        # than just module-scope statements.
        ("app.models", "devmode"),
        ("app.models", "quotas"),
        # app/auth.py imports `devmode`/`quotas` at module scope (register
        # needs both caps) and defers `from .licensing import
        # configured_host` inside one function (password-reset link
        # building). auth.py conflates the auth primitive with the
        # `auth_bp` route handlers in one file, so "auth layer" and
        # "registration route" are the same module here.
        ("app.auth", "devmode"),
        ("app.auth", "quotas"),
        ("app.auth", "licensing"),
        # app/auth.py and app/authz.py both defer/import
        # `app.tenancy`/`app.tenancy.authz` for `resolve_scopes` /
        # `platform_scopes` / `UNSCOPED_SCOPES` -- a token's scope bundle
        # cannot be resolved without knowing the tenant hierarchy, so auth
        # depends on tenancy in practice everywhere it mints or checks a
        # scope. Confirmed one-directional: app/tenancy/*.py has no import
        # of app.auth, app.authz or app.middleware (its own `.authz` /
        # `.middleware` references are its OWN submodules, not these).
        ("app.auth", "tenancy"),
        ("app.authz", "tenancy"),
        # app/proxy.py and app/product_access.py both call
        # `flags.product_gate_refusal` / `flags.flag_key` to decide whether
        # a product route is enabled before forwarding -- the proxy is the
        # choke point where the org-standard "every feature behind a
        # PostHog flag" gate (general.md) actually has to be checked for
        # product access, so this is licensing DECIDING something the
        # proxy layer enforces, the inverse of the peer relationship the
        # audit assumed. Confirmed one-directional: app/flags.py has no
        # app-internal imports of its own.
        ("app.proxy", "flags"),
        ("app.product_access", "flags"),
        # app/ratelimit.py (floor) defers `from .middleware import
        # get_current_user` inside `user_account_key()`, to key a rate
        # limit by the authenticated caller's own id rather than by raw
        # IP/email. Same shape as the models.py entries above -- a floor
        # primitive reaching up for one piece of request context. Confirmed
        # one-directional: app/middleware.py has no reference to
        # app.ratelimit.
        ("app.ratelimit", "middleware"),
    }
)


def _real_violations() -> set[tuple[str, str, str, str]]:
    """Every sideways/upward edge that actually exists in the tree today.

    ``(source module, target module, source layer, target layer)``. Shared
    by both tests below so the "found" and "allowed" sides are computed
    from the identical scan.
    """
    violations: set[tuple[str, str, str, str]] = set()
    for path in _discover_modules():
        own_module = _module_name(path)
        source_layer = _layer_of(own_module)
        is_init = path.name == "__init__.py"
        for target in _imports_in(path, own_module, is_init):
            if target == own_module or not target.startswith("app."):
                continue
            target_component = _component(target)
            if target_component is None:
                continue
            target_layer = _layer_of(target)
            if source_layer == target_layer:
                continue  # same layer (including cross-component peers)
            if _RANK[source_layer] > _RANK[target_layer]:
                continue  # strictly downward -- healthy
            violations.add((own_module, target, source_layer, target_layer))
    return violations


def test_no_illegal_layer_imports() -> None:
    """Every sideways/upward edge in ``app/`` is either absent or allow-listed.

    This is the actual gate: a NEW violation -- anything not already in
    :data:`ALLOWED_EXCEPTIONS` -- fails here, naming the exact edge. See
    Section C of the accompanying work for proof this can fail: a
    deliberately introduced sideways import was run through this exact
    assertion and produced a red failure naming it, before being reverted.
    """
    found = _real_violations()
    unexpected = {
        edge for edge in found if (edge[0], _component(edge[1])) not in ALLOWED_EXCEPTIONS
    }
    assert not unexpected, (
        "New sideways/upward layer import(s) found, not on the allow list:\n"
        + "\n".join(
            f"  {source} ({source_layer}) -> {target} ({target_layer})"
            for source, target, source_layer, target_layer in sorted(unexpected)
        )
        + "\n\nEither fix the import direction, or add a documented entry to "
        "ALLOWED_EXCEPTIONS in this file explaining why it is a scheduled, "
        "not sanctioned, exception."
    )


def test_exception_list_has_no_stale_entries() -> None:
    """Every :data:`ALLOWED_EXCEPTIONS` entry still corresponds to a real edge.

    A grandfather list nobody re-checks silently becomes a permission slip:
    an entry left in after its edge was fixed no longer documents a real
    exception, it just quietly widens what the next PR can get away with.
    Failing here means the entry should be deleted, not that anything is
    broken.
    """
    found_pairs = {(source, _component(target)) for source, target, _, _ in _real_violations()}
    stale = {entry for entry in ALLOWED_EXCEPTIONS if entry not in found_pairs}
    assert not stale, (
        "ALLOWED_EXCEPTIONS entries with no matching real violation -- "
        "remove them, the edge they described no longer exists:\n"
        + "\n".join(f"  {source} -> {target}" for source, target in sorted(stale))
    )


@pytest.mark.parametrize("path", _discover_modules(), ids=lambda p: str(p.relative_to(_APP_ROOT)))
def test_every_app_module_is_classified(path: Path) -> None:
    """Every file under ``app/`` resolves to a known layer.

    Parametrized per-file (rather than one assertion in a loop) so a new,
    unclassified module fails as its own named test case -- visible in the
    run summary as exactly which file needs a :data:`LAYER_OF` entry,
    instead of one opaque failure covering the whole tree.
    """
    _layer_of(_module_name(path))  # raises AssertionError if unclassified
