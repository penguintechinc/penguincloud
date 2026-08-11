"""Guards that DERIVE what must be gated instead of listing it.

Both findings this file exists for were the same shape: a guard that was
real but did not reach everything it was supposed to cover.

* ``product_gate_refusal`` ran at two call sites while ten other
  authenticated routes reached the connected product with decrypted
  credentials. Every one of them was individually correct-looking; the set
  was wrong, and nothing could tell.
* ``audit_export`` sat in ``NOT_YET_IMPLEMENTED`` while
  ``GET /api/v1/audit/export`` was fully built. The existing guard
  (:func:`test_a_built_feature_may_not_hide_in_not_yet_implemented`) only
  fires when a feature IS gated, so a built-but-ungated feature parked in
  that set could not trip it — by construction.

The fix for both is the same move already used for
``test_every_builder_has_a_rule_backing_it`` and for the
``default_for``-not-a-literal-map assertion in ``/features``: derive the
obligation from the code, so a NEW ungated route or a NEWLY built feature
fails the test on arrival rather than when someone remembers to update a
list.

A hand-maintained list of the ten routes would have passed today and been
wrong at the eleventh.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Final

import pytest

from app import licensing

_APP_DIR: Final[Path] = (
    Path(__file__).resolve().parents[2] / "services" / "portal-api" / "app"
)

#: Reaching one of these means the request touches the connected product
#: itself — an outbound call carrying decrypted credentials, or the shared
#: authorisation path that builds the context for one.
_PRODUCT_ENTRY_POINTS: Final[frozenset[str]] = frozenset(
    {"get_adapter", "resolve_product_context"}
)

#: The gate. Reaching this — directly, or through a helper that does — is
#: what makes a product-touching route gated.
_GATE: Final[str] = "product_gate_refusal"

#: Routes that reach a product and are deliberately NOT gated.
#:
#: Empty, and it should stay that way. It exists so that an exception is a
#: named decision with a reason beside it rather than a silent omission —
#: the failure mode being guarded against here in the first place. A
#: candidate would be a health/status route that must answer while a module
#: is switched off; today's ``GET /<id>/health`` reads a stored column and
#: never reaches the product, so it does not need to be here.
PRODUCT_ROUTES_INTENTIONALLY_UNGATED: Final[frozenset[str]] = frozenset()


def _iter_app_modules() -> list[tuple[Path, ast.Module]]:
    return [
        (path, ast.parse(path.read_text(encoding="utf-8")))
        for path in sorted(_APP_DIR.rglob("*.py"))
    ]


def _called_names(node: ast.AST) -> set[str]:
    """Every function name called anywhere inside ``node``."""
    names: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Attribute):
            names.add(func.attr)
        elif isinstance(func, ast.Name):
            names.add(func.id)
    return names


def _build_call_graph() -> tuple[dict[str, set[str]], dict[str, list[str]]]:
    """``name -> names it calls``, plus where each name is defined."""
    calls: dict[str, set[str]] = {}
    definitions: dict[str, list[str]] = {}
    for path, tree in _iter_app_modules():
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            definitions.setdefault(node.name, []).append(str(path))
            calls.setdefault(node.name, set()).update(_called_names(node))
    return calls, definitions


def _route_functions() -> dict[str, tuple[str, str]]:
    """``function name -> (module, rule)`` for every registered route."""
    routes: dict[str, tuple[str, str]] = {}
    for path, tree in _iter_app_modules():
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                func = decorator.func
                if not (isinstance(func, ast.Attribute) and func.attr == "route"):
                    continue
                rule = ""
                if decorator.args and isinstance(decorator.args[0], ast.Constant):
                    rule = str(decorator.args[0].value)
                routes[node.name] = (path.name, rule)
    return routes


def _reachable_from(name: str, calls: dict[str, set[str]]) -> set[str]:
    """Transitive closure of calls, resolved by bare name.

    Bare-name resolution over-approximates. That is safe in the direction
    that matters here only because every name this test decides on is
    asserted to be defined exactly once (see
    :func:`test_the_names_this_guard_resolves_are_unambiguous`) — otherwise
    a same-named local helper elsewhere could make an ungated route look
    gated, which is the one error this file must not make.
    """
    seen: set[str] = set()
    queue = [name]
    while queue:
        current = queue.pop()
        for callee in calls.get(current, set()):
            if callee not in seen:
                seen.add(callee)
                queue.append(callee)
    return seen


class TestEveryProductRouteIsGated:
    """The kill switch must reach every route that reaches a product."""

    @pytest.fixture(scope="class")
    def analysis(self) -> dict[str, Any]:
        calls, definitions = _build_call_graph()
        routes = _route_functions()
        reach = {name: _reachable_from(name, calls) for name in routes}
        return {
            "calls": calls,
            "definitions": definitions,
            "routes": routes,
            "reaching": {
                name
                for name, closure in reach.items()
                if closure & _PRODUCT_ENTRY_POINTS
            },
            "gated": {name for name, closure in reach.items() if _GATE in closure},
        }

    def test_the_names_this_guard_resolves_are_unambiguous(
        self, analysis: dict[str, Any]
    ) -> None:
        """Bare-name resolution is only sound while the names are unique."""
        for name in {*_PRODUCT_ENTRY_POINTS, _GATE}:
            sites = analysis["definitions"].get(name, [])
            assert len(sites) == 1, f"{name} defined in {len(sites)} places: {sites}"

    def test_the_scanner_finds_the_routes_it_is_meant_to_check(
        self, analysis: dict[str, Any]
    ) -> None:
        """A set-difference check passes vacuously on an empty left side."""
        assert len(analysis["routes"]) > 20, len(analysis["routes"])
        # Named because each is a different shape of product access: the
        # raw proxy, the shared typed path, and a route that builds its own
        # adapter context.
        for known in ("proxy_request", "create_resource", "get_product_schema"):
            assert known in analysis["reaching"], sorted(analysis["reaching"])

    def test_every_product_touching_route_is_gated(
        self, analysis: dict[str, Any]
    ) -> None:
        """Derived, not listed — an eleventh route cannot arrive ungated.

        ``penguincloud.{product}`` set to false left resource create still
        creating and resource actions still executing, because the gate ran
        only at connection create and in the proxy.
        """
        ungated = (
            analysis["reaching"]
            - analysis["gated"]
            - PRODUCT_ROUTES_INTENTIONALLY_UNGATED
        )

        assert not ungated, (
            "routes reach the connected product with no flag/licence check: "
            + ", ".join(
                f"{name} ({analysis['routes'][name][0]}{analysis['routes'][name][1]})"
                for name in sorted(ungated)
            )
            + ". Gate them, or add them to "
            "PRODUCT_ROUTES_INTENTIONALLY_UNGATED with the reason."
        )

    def test_the_exception_list_names_real_routes(
        self, analysis: dict[str, Any]
    ) -> None:
        """A stale exception silently re-opens the hole it documented."""
        unknown = PRODUCT_ROUTES_INTENTIONALLY_UNGATED - set(analysis["routes"])
        assert not unknown, sorted(unknown)


def _implementation_evidence(feature: str) -> list[str]:
    """Places in the app that look like an implementation of ``feature``.

    Matching is on SEGMENTS, never substrings: ``byok_ai`` must not match
    ``/api/...`` because "ai" happens to sit inside "api". A feature counts
    as implemented when some route rule or view-function name contains every
    word of its name as a distinct segment.
    """
    wanted = set(feature.split("_"))
    hits: list[str] = []
    for name, (module, rule) in _route_functions().items():
        segments = {
            part
            for chunk in (rule, name)
            for part in chunk.replace("<", "/").replace(">", "/").replace("-", "/")
            .replace("_", "/")
            .split("/")
            if part
        }
        if wanted <= segments:
            hits.append(f"{module}:{name} ({rule})")
    return sorted(hits)


class TestNothingBuiltHidesInNotYetImplemented:
    """The converse the existing guard could not express.

    ``test_a_built_feature_may_not_hide_in_not_yet_implemented`` intersects
    the set with GATED features, so it can only fire once a gate exists. A
    feature that is built and NOT gated — the actual failure — is invisible
    to it. This asks the opposite question of the code: does an
    implementation exist for something we are claiming is unbuilt?
    """

    def test_the_detector_recognises_a_known_implementation(self) -> None:
        """Non-vacuity, and it pins the exact bug that motivated this.

        ``audit_export`` was parked in NOT_YET_IMPLEMENTED while
        ``GET /api/v1/audit/export`` shipped CSV and JSON. If this assertion
        ever stops finding it, the detector has gone blind and every check
        below is passing for the wrong reason.
        """
        assert _implementation_evidence("audit_export"), (
            "the implementation detector no longer sees /audit/export — "
            "every NOT_YET_IMPLEMENTED assertion below is now vacuous"
        )

    def test_the_detector_does_not_fire_on_everything(self) -> None:
        """A detector that matches anything proves nothing."""
        assert not _implementation_evidence("no_such_capability_at_all")

    @pytest.mark.parametrize(
        "feature", sorted(licensing.NOT_YET_IMPLEMENTED)
    )
    def test_no_implementation_exists_for_an_unbuilt_feature(
        self, feature: str
    ) -> None:
        """Being in this set exempts a feature from the mint-vs-enforce
        guard, so the set must not contain anything that is actually built.
        """
        evidence = _implementation_evidence(feature)
        assert not evidence, (
            f"'{feature}' is listed as not yet implemented, but looks built: "
            f"{evidence}. Gate it and remove it from NOT_YET_IMPLEMENTED."
        )

    def test_the_set_is_not_empty(self) -> None:
        """Guards the parametrised check above from vanishing silently."""
        assert licensing.NOT_YET_IMPLEMENTED
