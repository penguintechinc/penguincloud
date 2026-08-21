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
* **The tenant-scoped table set is derived from one file's syntax.**
  ``TENANT_SCOPED_TABLES`` is every class in ``models_sqlalchemy.py`` whose
  body assigns a column literally named ``tenant_id`` -- the same signal
  ``_table_access`` already reads to decide a reader is FILTERED. A table
  scoped through a differently named column, scoped only by a join to a
  tenant-scoped parent (never carrying its own ``tenant_id``), or declared
  only in a raw Alembic migration with no matching class in that file, is
  invisible to this derivation the same way an aliased or raw-SQL access is
  invisible to ``_table_access`` itself.
* **A reader with no tenant predicate is not automatically a leak.**
  ``READERS_WITHOUT_TENANT_PREDICATE`` excuses specific ``(module,
  function)`` pairs whose predicate is legitimately not "this table's own
  ``tenant_id``" -- a load-by-primary-key helper whose every call site
  checks ``require_tenant_scope``/``resolve_effective_role`` against the
  loaded row's tenant_id before using it, a deployment-wide quota
  aggregate, or a query correctly scoped by the caller's own ``user_id``
  instead. Each entry is a named, individually justified claim, not a
  blanket waiver -- see the comment beside each. A future reader that
  *looks* like one of these shapes but isn't (skips the downstream check,
  or leaks the aggregate to a tenant-scoped response) is not covered by
  this list; it is covered by the fact that adding it to the list is the
  only way to silence the failure, which puts a reviewer's eyes on it.
* **A table with zero readers is indistinguishable, to this scanner, from a
  table the reader-detection AST walk has gone blind on.**
  ``TABLES_WITH_NO_READERS_TODAY`` names ``tenant_product_features``
  specifically rather than relaxing the non-vacuity assertion generally, so
  a genuine scanner regression on a table that DOES have readers (every
  other entry in ``TENANT_SCOPED_TABLES``) still fails loudly.
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


#: Path to the single source of table structure. Its own module docstring
#: says it: "SQLAlchemy Schema Models... DO NOT use these for runtime
#: queries" -- models.py performs the queries, this file declares the
#: columns, so it's the one place a `tenant_id` column is decided rather
#: than merely used.
_SCHEMA_PATH: Final[Path] = _APP_DIR / "models_sqlalchemy.py"


def _schema_tenant_scoped_tables() -> frozenset[str]:
    """Every table whose class declares a ``tenant_id`` column.

    Derived from the schema, not hand-maintained: a table becomes
    tenant-scoped, by construction, the moment a developer gives it a
    ``tenant_id`` column, so reading that column back out is deriving from
    the same signal that made the table tenant-scoped in the first place.
    A hand-written list is what limited this guard to ``audit_logs`` alone
    for months; a new tenant-scoped table now arrives covered the moment
    its column exists, with no second step to remember.

    Walks both ``Assign`` (``tenant_id = Column(...)``, every case in this
    file today) and ``AnnAssign`` (``tenant_id: Any = Column(...)``, the
    style already used for ``parent_tenant_id``/``kind``/``depth`` on
    ``Tenant``) so a future column doesn't silently fall through a form
    this scanner didn't anticipate.
    """
    tree = ast.parse(_SCHEMA_PATH.read_text(encoding="utf-8"))
    tables: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        tablename: str | None = None
        has_tenant_id = False
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                targets: list[ast.expr] = stmt.targets
            elif isinstance(stmt, ast.AnnAssign) and stmt.target is not None:
                targets = [stmt.target]
            else:
                continue
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id == "__tablename__" and isinstance(stmt.value, ast.Constant):
                    tablename = str(stmt.value.value)
                elif target.id == "tenant_id":
                    has_tenant_id = True
        if tablename and has_tenant_id:
            tables.add(tablename)
    return frozenset(tables)


#: Tables whose rows belong to exactly one tenant, so that a query without a
#: tenant predicate returns other customers' data. Derived from the schema
#: — see :func:`_schema_tenant_scoped_tables`.
TENANT_SCOPED_TABLES: Final[frozenset[str]] = _schema_tenant_scoped_tables()

#: Tenant-scoped tables that are ALSO commercially licence-gated (Enterprise
#: "audit & compliance", per docs/APP_STANDARDS.md's tier table). This is
#: deliberately a small hand-picked subset of ``TENANT_SCOPED_TABLES``, not
#: the whole set: the tier model gates scale and structure, not features
#: (APP_STANDARDS.md "License Tiers"), so a tenant-scoped table like
#: ``product_connections`` is full-featured on every tier and must NOT
#: demand a ``require_feature`` gate just for being tenant-scoped. Only
#: ``audit_logs`` is named here today because auditability/compliance is
#: the one thing the tier table actually sells.
LICENCE_GATED_TENANT_TABLES: Final[frozenset[str]] = frozenset({"audit_logs"})

#: Readers of a tenant-scoped table that correctly have no ``tenant_id``
#: predicate of their own. Keyed ``(module, function)`` like
#: ``_tenant_table_readers``. Every entry is a named, individually
#: justified exception — see the comment beside each — not a blanket
#: waiver; :func:`test_the_no_predicate_exceptions_name_real_readers` and
#: the shape of the check itself (a reader either matches a name here or
#: fails the build) are what keep it from silently growing.
#:
#: Two shapes recur:
#:
#: * LOAD-THEN-CHECK — the function's job is "look this row up by its own
#:   primary key before the caller knows which tenant owns it".
#:   ``require_tenant_scope``/``resolve_effective_role`` is checked against
#:   the LOADED row's own ``tenant_id`` at every call site before the
#:   result is used or returned — the predicate exists, one hop later than
#:   this scanner can see. ``require_tenant_scope``'s own docstring names
#:   this pattern: "routes that must load a resource before they know which
#:   tenant owns it."
#: * DEPLOYMENT-WIDE / DIFFERENTLY-SCOPED — the read is deliberately not
#:   tenant-scoped at all: a licence-quota aggregate counted across the
#:   whole deployment (documented as such at its definition), or a query
#:   correctly scoped by the caller's own ``user_id`` instead of a tenant.
READERS_WITHOUT_TENANT_PREDICATE: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        # LOAD-THEN-CHECK. Verified every call site (products.py, discovery.py,
        # product_access.py, proxy.py) authorizes against the loaded row's
        # conn["tenant_id"] via require_tenant_scope/resolve_effective_role
        # before the connection is used or returned.
        ("models.py", "get_product_connection_by_id"),
        ("models.py", "get_product_connection_raw"),
        # LOAD-THEN-CHECK, narrower: re-reads the row it just inserted by the
        # row's own freshly generated id. The tenant_id written into that row
        # was already authorized by the caller (require_tenant_scope) before
        # add_tenant_member ran.
        ("models.py", "add_tenant_member"),
        # DEPLOYMENT-WIDE. "Delegated tenant admins across the DEPLOYMENT" —
        # see the docstring on quotas.count_tenant_admins for why a per-tenant
        # count would be wrong here, not merely unfiltered.
        ("quotas.py", "count_tenant_admins"),
        # DEPLOYMENT-WIDE. Same shape as count_tenant_admins — the Free-tier
        # 1,000-object quota is deployment-wide by definition; see
        # quotas.count_objects's docstring.
        ("quotas.py", "count_objects"),
        # DIFFERENTLY-SCOPED. "All tenants a user is a member of" is
        # correctly scoped by user_id, not tenant_id — spanning tenants is
        # the entire point of the query, and it discloses nothing beyond the
        # calling user's own memberships.
        ("models.py", "get_user_tenants"),
        # DEPLOYMENT-WIDE, INTERNAL ONLY. Feeds the background health poller,
        # which sweeps every connection each interval regardless of tenant;
        # see get_active_product_connections's docstring. Its only caller is
        # health_poller.py — never a per-tenant HTTP response.
        ("models.py", "get_active_product_connections"),
    }
)

#: Tenant-scoped tables with ZERO readers anywhere in the app today.
#:
#: Not a security exception — nothing reads them, so nothing can leak them.
#: A NAMED allowance so a genuinely-unread table doesn't trip the "the
#: scanner has stopped working" vacuity guard the way an actual scanner
#: regression would. ``tenant_product_features`` is written (creation) and
#: deleted (``tenants.py`` cascade on tenant delete) but has no reader yet —
#: ``app/middleware.py``'s ``require_feature`` documents the read as an open
#: ``TODO(phase-1b)`` and DENIES in its absence, so the gap fails closed
#: rather than open. The moment it gains a reader, that reader falls under
#: the ordinary tenant-predicate assertion like any other and this entry
#: must come out — :func:`test_the_no_reader_tables_are_confirmed_unread`
#: fails loudly if it doesn't.
TABLES_WITH_NO_READERS_TODAY: Final[frozenset[str]] = frozenset({"tenant_product_features"})

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
#: RULED ON AND SETTLED — do not "fix" this by deleting the entry.
#:
#: The tier model gates SCALE AND STRUCTURE, NOT FEATURES: every tier gets
#: all modules with full features, and "a single free user experiences the
#: whole product… never a locked or crippled module". A dashboard whose
#: activity feed is dead on Free is exactly that crippled module.
#:
#: What Enterprise sells is auditability and compliance — the searchable,
#: filterable, exportable trail, which is what ``/api/v1/audit/logs`` and
#: ``/api/v1/audit/export`` are. A ≤100-row unfiltered recent-activity
#: widget is not that product; it is the dashboard working.
#:
#: Because this route IS reachable on every tier, its response projection
#: matters more than the licensed ones', not less: it serves the least
#: gated view of the most sensitive table in the portal. It returned the
#: raw audit row until that was fixed — see app/audit_view.py and
#: tests/api/test_audit_response_shape.py.
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
    """Every route serving a tenant-private table must scope it.

    A subset — today just ``audit_logs`` — must ALSO be licence-gated; see
    ``LICENCE_GATED_TENANT_TABLES``. The two obligations are checked
    separately on purpose: tenant scoping is a security property that every
    tenant-scoped table owes unconditionally, licence gating is a
    commercial one that only the tables the tier model actually sells owe.

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

        if table in TABLES_WITH_NO_READERS_TODAY:
            assert not readers, (
                f"{table} now has a reader ({sorted(readers)}) but is listed "
                f"in TABLES_WITH_NO_READERS_TODAY as unread — remove it from "
                f"that set so the new reader gets the tenant-predicate check "
                f"below instead of being silently exempted"
            )
            return

        assert readers, (
            f"found no readers of {table} at all — the scanner has stopped "
            f"working and this check is passing vacuously"
        )

        unscoped = [
            f"{module}:{name}"
            for (module, name), filtered in readers.items()
            if not filtered and (module, name) not in READERS_WITHOUT_TENANT_PREDICATE
        ]
        assert not unscoped, (
            f"these functions read {table} without a tenant predicate, so "
            f"they return every tenant's rows: {unscoped}. If this is a "
            f"deliberate exception, name it in READERS_WITHOUT_TENANT_PREDICATE "
            f"with a reason; do not silence it here."
        )

    def test_the_no_predicate_exceptions_name_real_readers(self) -> None:
        """A stale exception silently re-opens the hole it documented."""
        all_readers: set[tuple[str, str]] = set()
        for table in TENANT_SCOPED_TABLES:
            all_readers |= set(_tenant_table_readers(table))
        unknown = READERS_WITHOUT_TENANT_PREDICATE - all_readers
        assert not unknown, sorted(unknown)

    def test_the_no_reader_tables_are_confirmed_unread(self) -> None:
        """A stale entry here would hide a real vacuous-pass regression.

        Belt-and-braces alongside the per-table assertion above: this also
        catches ``TABLES_WITH_NO_READERS_TODAY`` naming a table that fell out
        of the schema entirely (renamed/dropped), which the per-table
        parametrize would simply stop covering rather than fail.
        """
        unknown = TABLES_WITH_NO_READERS_TODAY - TENANT_SCOPED_TABLES
        assert not unknown, sorted(unknown)

    def test_the_schema_scanner_finds_more_than_one_table(self) -> None:
        """Non-vacuity, named: the defect this guard exists to fix.

        A hand-written ``{"audit_logs"}`` would have passed every check
        above too. Pinning the other tenant-scoped tables by name is what
        proves the derivation actually ran against the schema instead of
        quietly returning the same single entry.
        """
        assert len(TENANT_SCOPED_TABLES) > 1, sorted(TENANT_SCOPED_TABLES)
        for known in (
            "audit_logs",
            "tenant_members",
            "product_connections",
            "tenant_product_features",
            "product_tenant_map",
        ):
            assert known in TENANT_SCOPED_TABLES, sorted(TENANT_SCOPED_TABLES)

    @pytest.mark.parametrize("table", sorted(LICENCE_GATED_TENANT_TABLES))
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
        """The licence exception list is commercial, never a security waiver.

        Being unlicensed is a pricing decision someone can make. Reading
        another tenant's rows is not, so ``AUDIT_ROUTES_INTENTIONALLY_UNLICENSED``
        specifically may never double as a tenant-isolation waiver — asserted
        here so nobody later "extends" this list to silence an isolation
        failure. (``READERS_WITHOUT_TENANT_PREDICATE`` is the separate,
        individually-justified mechanism for a reader that legitimately has
        no tenant_id predicate of its own; this test is not about that list.)
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
