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
wrong at the eleventh. The same move found a FOURTH audit route
(``dashboard_activity``) that three rounds of review had not enumerated.

WHAT THESE GUARDS CANNOT SEE
============================
Stated because a guard whose blind spots are undocumented is how three of
these defects were shipped in the first place. None of the below is wrong
today; all of it is where to look next.

* **The route scanner assumes the ``@bp.route(...)`` decorator form.** True
  for all 99 routes today. A route registered via ``add_url_rule``, a
  class-based view, or a blueprint built in a loop is invisible, and an
  invisible route is an ungated one as far as these checks are concerned.
* **Call resolution is by bare NAME.** ``test_the_names_this_guard_resolves_
  are_unambiguous`` pins the three names the product-gate check decides on,
  but six route names already collide with adapter method names elsewhere in
  the package. A future homonym could make an ungated route look gated. The
  audit reader set is keyed by ``(module, name)`` for this reason; the
  product-gate closure is not.
* **The not-yet-implemented detector is a HEURISTIC** — a segment match over
  the route rule and the view name. A rename defeats it. More importantly,
  a capability that is not a route (``external_kms``, ``whitelabel``,
  ``byok_ai``) can never produce evidence, so those entries pass
  structurally vacuously; non-vacuity is pinned for ``audit_export`` alone,
  which is the only one that has ever been wrong.
* **"Reads a tenant-scoped table" is syntactic.** It matches ``db.<table>``
  plus a ``.select``/``.count`` in the same function. A read reached through
  a variable alias, raw SQL (``executesql``), or a helper that takes the
  table as a parameter is invisible. Likewise "filters by tenant" matches
  the presence of ``db.<table>.tenant_id`` anywhere in the function — it
  cannot tell a predicate from a projection, so it proves a tenant column is
  MENTIONED, not that the query is correctly restricted. The behavioural
  test in ``test_audit_isolation.py`` is what proves restriction; this one
  exists to catch the route nobody wrote a behavioural test for.
* **One table is enumerated** (``audit_logs``). Other tenant-scoped tables
  are not checked; adding one is adding a name to
  ``TENANT_SCOPED_TABLES``.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Final

import pytest
from app import licensing

_APP_DIR: Final[Path] = Path(__file__).resolve().parents[2] / "services" / "portal-api" / "app"

#: Reaching one of these means the request touches the connected product
#: itself — an outbound call carrying decrypted credentials, or the shared
#: authorisation path that builds the context for one.
_PRODUCT_ENTRY_POINTS: Final[frozenset[str]] = frozenset({"get_adapter", "resolve_product_context"})

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
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            definitions.setdefault(node.name, []).append(str(path))
            calls.setdefault(node.name, set()).update(_called_names(node))
    return calls, definitions


def _route_functions() -> dict[str, tuple[str, str]]:
    """``function name -> (module, rule)`` for every registered route."""
    routes: dict[str, tuple[str, str]] = {}
    for path, tree in _iter_app_modules():
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
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
        """Analysis."""
        calls, definitions = _build_call_graph()
        routes = _route_functions()
        reach = {name: _reachable_from(name, calls) for name in routes}
        return {
            "calls": calls,
            "definitions": definitions,
            "routes": routes,
            "reaching": {
                name for name, closure in reach.items() if closure & _PRODUCT_ENTRY_POINTS
            },
            "gated": {name for name, closure in reach.items() if _GATE in closure},
        }

    def test_the_names_this_guard_resolves_are_unambiguous(self, analysis: dict[str, Any]) -> None:
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

    def test_every_product_touching_route_is_gated(self, analysis: dict[str, Any]) -> None:
        """Derived, not listed — an eleventh route cannot arrive ungated.

        ``penguincloud.{product}`` set to false left resource create still
        creating and resource actions still executing, because the gate ran
        only at connection create and in the proxy.
        """
        ungated = analysis["reaching"] - analysis["gated"] - PRODUCT_ROUTES_INTENTIONALLY_UNGATED

        assert not ungated, (
            "routes reach the connected product with no flag/licence check: "
            + ", ".join(
                f"{name} ({analysis['routes'][name][0]}{analysis['routes'][name][1]})"
                for name in sorted(ungated)
            )
            + ". Gate them, or add them to "
            "PRODUCT_ROUTES_INTENTIONALLY_UNGATED with the reason."
        )

    def test_the_exception_list_names_real_routes(self, analysis: dict[str, Any]) -> None:
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
            for part in chunk.replace("<", "/")
            .replace(">", "/")
            .replace("-", "/")
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

    @pytest.mark.parametrize("feature", sorted(licensing.NOT_YET_IMPLEMENTED))
    def test_no_implementation_exists_for_an_unbuilt_feature(self, feature: str) -> None:
        """Nothing declared unbuilt may have an implementation.

        Being in this set exempts a feature from the mint-vs-enforce guard,
        so the set must not contain anything that is actually built.
        """
        evidence = _implementation_evidence(feature)
        assert not evidence, (
            f"'{feature}' is listed as not yet implemented, but looks built: "
            f"{evidence}. Gate it and remove it from NOT_YET_IMPLEMENTED."
        )

    def test_the_set_is_not_empty(self) -> None:
        """Guards the parametrised check above from vanishing silently."""
        assert licensing.NOT_YET_IMPLEMENTED


#: Tables whose rows belong to exactly one tenant, so that a query without a
#: tenant predicate returns other customers' data.
#:
#: One name today. Extending the guard to another table is adding a name
#: here, which is the point of naming them at all — the alternative, a
#: hand-written list of "routes that serve audit data", is what let a third
#: audit route exist for months without either gate.
TENANT_SCOPED_TABLES: Final[frozenset[str]] = frozenset({"audit_logs"})

#: Calls that turn a query into rows. An INSERT (`async_insert`) is not a
#: read, and audit rows must be written on every tier — see
#: `models.create_audit_log`.
_READ_CALLS: Final[frozenset[str]] = frozenset({"select", "count"})

#: Routes that read a tenant-scoped table and are deliberately NOT licence
#: gated. An entry here excuses the LICENCE gate and nothing else — the
#: tenant-predicate assertion applies to every reader without exception,
#: because that one is a security property rather than a commercial one.
#:
#: ``dashboard_activity`` (``GET /api/v1/dashboard/activity``) was found by
#: this guard, not by review. It reads ``audit_logs`` correctly scoped to
#: one tenant behind ``tenants:read``, and returns at most 100 recent rows
#: with no filtering, no pagination and no export.
#:
#: The judgement: what the tier table sells at Enterprise is
#: "auditability & compliance" — querying, filtering and exporting the
#: trail, which is what ``/api/v1/audit/logs`` and ``/api/v1/audit/export``
#: are. A bounded recent-activity card on the dashboard is the product's
#: own UI, and gating it would leave a visibly broken dashboard on Free,
#: which is the "locked or crippled module" the tier model forbids outright.
#:
#: FLAGGED FOR CONFIRMATION rather than assumed — see the report. If the
#: answer is that any read of the trail is Enterprise, deleting this entry
#: is the whole change, and the test will then require the gate.
AUDIT_ROUTES_INTENTIONALLY_UNLICENSED: Final[frozenset[str]] = frozenset({"dashboard_activity"})


def _table_access(node: ast.AST, table: str) -> tuple[bool, bool]:
    """``(reads the table, filters it by tenant_id)`` for one function."""
    touches_table = False
    filters_by_tenant = False
    for child in ast.walk(node):
        if not isinstance(child, ast.Attribute):
            continue
        # db.<table>
        if child.attr == table and isinstance(child.value, ast.Name) and child.value.id == "db":
            touches_table = True
        # db.<table>.tenant_id
        if (
            child.attr == "tenant_id"
            and isinstance(child.value, ast.Attribute)
            and child.value.attr == table
        ):
            filters_by_tenant = True
    reads = touches_table and bool(_called_names(node) & _READ_CALLS)
    return reads, filters_by_tenant


def _tenant_table_readers(table: str) -> dict[tuple[str, str], bool]:
    """``(module, function) -> is tenant-filtered`` for readers of ``table``.

    Keyed by module AND name on purpose: ``get_audit_logs`` exists in both
    ``audit.py`` (a route) and ``auth_features.py`` (its helper), and a
    name-keyed dict would silently keep one and drop the other — losing a
    reader is precisely the failure this guard exists to prevent.
    """
    readers: dict[tuple[str, str], bool] = {}
    for path, tree in _iter_app_modules():
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            reads, filtered = _table_access(node, table)
            if reads:
                readers[(path.name, node.name)] = filtered
    return readers


def _reader_names(table: str) -> set[str]:
    """Bare names of every reader, for call-graph matching."""
    return {name for _, name in _tenant_table_readers(table)}


def _serves_table(route: str, calls: dict[str, set[str]], readers: set[str]) -> bool:
    """True when a route reads the table itself or calls something that does.

    The route's own name is included deliberately: ``audit.py``'s two routes
    ARE the readers, and a closure that only looked at callees found neither.
    """
    return bool(({route} | _reachable_from(route, calls)) & readers)


class TestTenantScopedTablesAreNotReadGlobally:
    """Every route serving a tenant-private table must scope AND licence it.

    ``GET /api/v1/users/audit-logs`` read every audit row in the deployment
    and carried no licence gate, so it both leaked across tenants and walked
    around the Enterprise wall on the other two audit routes. Neither
    existing guard could see it: the mint-vs-enforce check is satisfied by a
    single enforcement site anywhere, and the not-yet-implemented converse
    only interrogates features claimed to be unbuilt.

    Derived from the code, per table, so a fourth audit route cannot arrive
    unscoped.
    """

    @pytest.mark.parametrize("table", sorted(TENANT_SCOPED_TABLES))
    def test_every_reader_filters_by_tenant(self, table: str) -> None:
        """A read with no tenant predicate returns other customers' rows."""
        readers = _tenant_table_readers(table)

        assert readers, (
            f"found no readers of {table} at all — the scanner has stopped "
            f"working and this check is passing vacuously"
        )

        unscoped = [
            f"{module}:{name}" for (module, name), filtered in readers.items() if not filtered
        ]
        assert not unscoped, (
            f"these functions read {table} without a tenant predicate, so "
            f"they return every tenant's rows: {unscoped}"
        )

    @pytest.mark.parametrize("table", sorted(TENANT_SCOPED_TABLES))
    def test_every_route_reaching_a_reader_is_licence_gated(self, table: str) -> None:
        """Audit access is Enterprise; a third door makes the wall optional."""
        calls, _ = _build_call_graph()
        routes = _route_functions()
        readers = _reader_names(table)

        serving = {name: routes[name] for name in routes if _serves_table(name, calls, readers)}
        assert serving, (
            f"no route appears to serve {table} — the scanner has stopped "
            f"working and this check is passing vacuously"
        )

        ungated = {
            name: rule
            for name, rule in serving.items()
            if "require_feature" not in _reachable_from(name, calls)
            and name not in AUDIT_ROUTES_INTENTIONALLY_UNLICENSED
        }
        assert not ungated, (
            f"routes serve {table} with no licence gate: {ungated}. The "
            f"Enterprise wall on the other audit routes is only as strong "
            f"as the weakest door onto the same data."
        )

    def test_the_scanner_sees_all_three_audit_doors(self) -> None:
        """Non-vacuity, named: three routes serve this table, not one."""
        calls, _ = _build_call_graph()
        routes = _route_functions()
        readers = _reader_names("audit_logs")
        serving = {name for name in routes if _serves_table(name, calls, readers)}

        for known in (
            "get_audit_logs_endpoint",  # /api/v1/users/audit-logs
            "get_audit_logs",  # /api/v1/audit/logs
            "export_audit_logs",  # /api/v1/audit/export
        ):
            assert known in serving, sorted(serving)

    def test_the_unlicensed_exceptions_name_real_routes(self) -> None:
        """A stale exception silently re-opens the hole it documented."""
        unknown = AUDIT_ROUTES_INTENTIONALLY_UNLICENSED - set(_route_functions())
        assert not unknown, sorted(unknown)

    def test_an_exception_can_never_excuse_the_tenant_predicate(self) -> None:
        """The exception list is commercial, never a security waiver.

        Being unlicensed is a pricing decision someone can make. Reading
        another tenant's rows is not, so the tenant assertion above takes no
        exceptions at all — asserted here so nobody later "extends" this
        list to silence an isolation failure.
        """
        readers = _tenant_table_readers("audit_logs")
        for route in AUDIT_ROUTES_INTENTIONALLY_UNLICENSED:
            matching = [filtered for (_, name), filtered in readers.items() if name == route]
            assert matching, f"{route} no longer reads audit_logs"
            assert all(matching), f"{route} is exempt from LICENSING, not isolation"

    def test_the_writer_is_not_mistaken_for_a_reader(self) -> None:
        """Audit rows are WRITTEN on every tier; only reading is licensed.

        If the scanner counted `create_audit_log` as a reader it would
        demand a licence gate on writing, which would make audit a locked
        module — exactly what the tier model forbids.
        """
        assert "create_audit_log" not in _reader_names("audit_logs")
