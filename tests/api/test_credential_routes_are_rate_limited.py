"""Derived guard: every credential-accepting route reaches `rate_limited`.

F2, precisely
=============
Login, refresh, forgot-password, reset-password, register, and MFA verify
were unthrottled -- three `TODO(phase-3)` markers (app/mfa.py:87,129,194)
stood in for the real thing, and app/auth.py's login carried no protection
at all. A hand-written list of "the six routes that need this" would have
been exactly the kind of guard this codebase has already shipped with a
structural blind spot more than once (see test_gate_coverage_is_derived.py
and test_declared_dependencies_suffice.py's own docstrings) -- correct
today, silently wrong the day an eleventh route is added.

The checked set is DERIVED, from two structural signals, unioned
============================================================================
1. **Every unauthenticated route in a FRONT_DOOR_BLUEPRINTS blueprint** (no
   ``@auth_required``) -- the front door: register, login, refresh,
   forgot-password, reset-password, confirm-email, plus RFC 8628's
   device-authorize/device-token (app/device_auth.py, its own blueprint --
   see FRONT_DOOR_BLUEPRINTS' own docstring for why this is a set, not a
   second hardcoded string). Any FUTURE unauthenticated route added to
   either blueprint is automatically swept in, forcing a deliberate decision
   (rate limit it, or name it in ``CREDENTIAL_ROUTES_INTENTIONALLY_UNLIMITED``
   with a reason) rather than a silent gap.
2. **Any route, in any blueprint, whose call graph reaches a credential-
   verification primitive** -- ``verify_password_async`` (bcrypt),
   ``.verify()`` (pyotp TOTP), ``is_refresh_token_valid``,
   ``validate_password_reset_token``, ``validate_email_token``. This is
   what pulls in the three MFA routes AND
   ``PUT /api/v1/users/me/password`` (``app/users.py::change_password``) --
   authenticated, so invisible to signal 1, but it re-verifies the
   caller's current password on every call and was found by this scanner,
   not by re-reading the brief.

WHAT THIS GUARD CANNOT SEE
===========================
* **Call resolution is by bare NAME**, exactly like the two guards this
  one is modelled on. ``test_the_names_this_guard_resolves_are_unambiguous``
  pins that the five primitive names and ``rate_limited`` are each defined
  in exactly one place, which is what makes bare-name resolution sound
  here.
* **The route/decorator scanner assumes the ``@bp.route(...)`` decorator
  form** and reads decorator Call nodes for both ``auth_required`` and
  ``rate_limited`` by NAME. A route registered via ``add_url_rule`` or a
  gate applied only inside the function body (rather than as a decorator)
  is invisible to it.
* **A primitive called from a route via a call chain going THROUGH a
  decorator's own closure** (rather than the view function's body) would
  not be found — every current call site is a direct or one-hop call from
  the view body, which is what the reachable-from-name closure covers.
* **New credential-verification primitives are not auto-discovered.**
  Adding a sixth kind of secret check (a new hashing scheme, a webhook
  signature) is invisible until its function name is added to
  ``CREDENTIAL_VERIFICATION_PRIMITIVES``.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Final

import pytest

_APP_DIR: Final[Path] = Path(__file__).resolve().parents[2] / "services" / "portal-api" / "app"

#: Functions whose being CALLED means "this route is checking a secret
#: against a stored value" -- see module docstring signal 2.
CREDENTIAL_VERIFICATION_PRIMITIVES: Final[frozenset[str]] = frozenset(
    {
        "verify_password_async",  # bcrypt password compare (app/auth.py)
        "verify",  # pyotp TOTP.verify(...) -- scoped to auth.py/mfa.py by
        # construction: grep across services/portal-api/app confirms no
        # OTHER `.verify(` call site exists anywhere else in the package
        # (test_the_verify_primitive_is_not_a_false_positive_magnet below
        # pins that).
        "is_refresh_token_valid",
        "validate_password_reset_token",
        "validate_email_token",
        # RFC 8628 device authorization grant (app/device_auth.py). Both
        # .../device/approve and .../device/deny are AUTHENTICATED, so
        # FRONT_DOOR_BLUEPRINTS below never sees them -- same shape as
        # change_password, found by this signal and not the brief. Each
        # looks up a device authorization by the human-guessable user_code
        # (models.get_device_authorization_by_user_code) as its own
        # credential-verification step before mutating anything.
        "get_device_authorization_by_user_code",
        # .../device/token is unauthenticated (covered by signal 1 via
        # FRONT_DOOR_BLUEPRINTS), but named here too as defense in depth --
        # this IS a credential-verification primitive (device_code compared
        # by hash) independent of which blueprint currently declares the
        # route that calls it.
        "get_device_authorization_by_device_code_hash",
    }
)

#: The gate. A route reaching this, directly (as its own decorator) or
#: transitively, is rate limited.
RATE_LIMIT_GATE: Final[str] = "rate_limited"

#: Blueprints whose UNAUTHENTICATED routes are, by definition, the front
#: door -- see module docstring signal 1. Was a single "auth_bp" string
#: until app/device_auth.py (RFC 8628 device grant) added a second
#: unauthenticated credential-minting blueprint (.../device/authorize,
#: .../device/token) -- a set, not a second hardcoded name check, so a
#: THIRD such blueprint is one line here rather than a second missed spot.
FRONT_DOOR_BLUEPRINTS: Final[frozenset[str]] = frozenset({"auth_bp", "device_auth_bp"})

#: Routes matching either signal that are deliberately NOT rate limited,
#: each with a reason. Empty, and it should stay that way -- an entry here
#: is a named decision, not a silent gap (same convention as
#: PRODUCT_ROUTES_INTENTIONALLY_UNGATED in test_gate_coverage_is_derived.py
#: and AUDIT_ROUTES_INTENTIONALLY_UNLICENSED in
#: test_declared_dependencies_suffice.py).
CREDENTIAL_ROUTES_INTENTIONALLY_UNLIMITED: Final[frozenset[str]] = frozenset()


def _iter_app_modules() -> list[tuple[Path, ast.Module]]:
    return [
        (path, ast.parse(path.read_text(encoding="utf-8")))
        for path in sorted(_APP_DIR.rglob("*.py"))
    ]


def _called_names(node: ast.AST) -> set[str]:
    """Every function name called anywhere inside ``node`` (body AND decorators)."""
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


def _decorator_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute):
            names.add(target.attr)
        elif isinstance(target, ast.Name):
            names.add(target.id)
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


def _reachable_from(name: str, calls: dict[str, set[str]]) -> set[str]:
    """Transitive closure of calls, resolved by bare name (see module docstring)."""
    seen: set[str] = set()
    queue = [name]
    while queue:
        current = queue.pop()
        for callee in calls.get(current, set()):
            if callee not in seen:
                seen.add(callee)
                queue.append(callee)
    return seen


def _route_functions() -> dict[str, dict[str, Any]]:
    """``function name -> {module, blueprint, rule, decorators}`` for every route."""
    routes: dict[str, dict[str, Any]] = {}
    for path, tree in _iter_app_modules():
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            blueprint = None
            rule = ""
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                func = decorator.func
                if not (isinstance(func, ast.Attribute) and func.attr == "route"):
                    continue
                if isinstance(func.value, ast.Name):
                    blueprint = func.value.id
                if decorator.args and isinstance(decorator.args[0], ast.Constant):
                    rule = str(decorator.args[0].value)
            if blueprint is None:
                continue
            routes[node.name] = {
                "module": path.name,
                "blueprint": blueprint,
                "rule": rule,
                "decorators": _decorator_names(node),
            }
    return routes


class _Analysis:
    def __init__(self) -> None:
        self.calls, self.definitions = _build_call_graph()
        self.routes = _route_functions()
        self.reach = {name: _reachable_from(name, self.calls) for name in self.routes}

        front_door = {
            name
            for name, info in self.routes.items()
            if info["blueprint"] in FRONT_DOOR_BLUEPRINTS
            and "auth_required" not in info["decorators"]
        }
        verifies_a_credential = {
            name
            for name, closure in self.reach.items()
            if closure & CREDENTIAL_VERIFICATION_PRIMITIVES
        }
        self.credential_accepting = front_door | verifies_a_credential
        self.gated = {
            name
            for name, info in self.routes.items()
            if RATE_LIMIT_GATE in info["decorators"]
            or RATE_LIMIT_GATE in self.reach.get(name, set())
        }


@pytest.fixture(scope="module")
def analysis() -> _Analysis:
    """Build the route/call-graph analysis once per module -- it is read-only."""
    return _Analysis()


class TestScannerSeesWhatItIsMeantToCheck:
    """Non-vacuity: every assertion below is meaningless against an empty set."""

    def test_the_scanner_finds_a_realistic_number_of_routes(self, analysis: _Analysis) -> None:
        """A route count this low would mean the AST walk stopped working."""
        assert len(analysis.routes) > 40, len(analysis.routes)

    def test_the_names_this_guard_resolves_are_unambiguous(self, analysis: _Analysis) -> None:
        """Bare-name resolution is only sound while these names are unique.

        ``verify`` is deliberately excluded: it names pyotp's
        ``TOTP.verify`` method, an external-library attribute call with no
        local ``def verify`` anywhere in this package to collide with --
        see ``test_the_verify_primitive_is_not_a_false_positive_magnet``
        for the check that instead bounds ITS blast radius (by call site,
        not by definition count).
        """
        for name in {*CREDENTIAL_VERIFICATION_PRIMITIVES, RATE_LIMIT_GATE} - {"verify"}:
            sites = analysis.definitions.get(name, [])
            assert len(sites) == 1, f"{name} defined in {len(sites)} places: {sites}"

    def test_the_verify_primitive_is_not_a_false_positive_magnet(self) -> None:
        """`.verify(` is a common method name -- pin that it stays scoped here.

        If this ever finds a call site outside auth.py/mfa.py, `verify` in
        CREDENTIAL_VERIFICATION_PRIMITIVES would start pulling in unrelated
        routes (or -- the safe-but-wrong direction -- an unrelated `.verify(`
        call inside a genuinely credential-accepting route would already be
        covered, but a call OUTSIDE any route would falsely mark a caller
        of that function as credential-accepting).
        """
        hits: list[str] = []
        for path, tree in _iter_app_modules():
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "verify"
                ):
                    hits.append(path.name)
        assert hits, "the .verify( scanner found nothing -- it has stopped working"
        assert set(hits) <= {"auth.py", "mfa.py"}, sorted(set(hits))

    def test_the_front_door_signal_finds_the_known_unauthenticated_routes(
        self, analysis: _Analysis
    ) -> None:
        """Signal 1 (module docstring) must resolve to the brief's own list."""
        front_door = {
            name
            for name, info in analysis.routes.items()
            if info["blueprint"] in FRONT_DOOR_BLUEPRINTS
            and "auth_required" not in info["decorators"]
        }
        for known in ("login", "register", "refresh", "forgot_password", "reset_password"):
            assert known in front_door, sorted(front_door)

    def test_the_front_door_signal_covers_the_device_authorization_routes(
        self, analysis: _Analysis
    ) -> None:
        """RFC 8628's two unauthenticated routes are swept in by blueprint, not by name.

        device_authorize/device_token are new; this pins that
        FRONT_DOOR_BLUEPRINTS -- not a per-route exception -- is what finds
        them, so a THIRD unauthenticated route added to device_auth_bp
        later is covered without anyone touching this file again.
        """
        front_door = {
            name
            for name, info in analysis.routes.items()
            if info["blueprint"] in FRONT_DOOR_BLUEPRINTS
            and "auth_required" not in info["decorators"]
        }
        assert "device_authorize" in front_door, sorted(front_door)
        assert "device_token" in front_door, sorted(front_door)

    def test_the_verification_signal_finds_the_known_routes(self, analysis: _Analysis) -> None:
        """Signal 2 (module docstring) must resolve to every known verifier, plus the bonus find."""
        known_routes = (
            "verify_mfa",
            "disable_mfa_endpoint",
            "regenerate_backup_codes",
            "change_password",  # app/users.py -- found by the scanner, not the brief
        )
        for known in known_routes:
            assert known in analysis.credential_accepting, sorted(analysis.credential_accepting)

    def test_the_credential_accepting_set_is_not_the_whole_app(self, analysis: _Analysis) -> None:
        """A predicate matching everything proves nothing was actually derived."""
        assert len(analysis.credential_accepting) < len(analysis.routes)


class TestEveryCredentialAcceptingRouteIsRateLimited:
    """The gate itself: F2 -- see module docstring for the derived checked set."""

    def test_every_credential_accepting_route_reaches_the_gate(self, analysis: _Analysis) -> None:
        """The actual guard: an ungated route fails this, by name, with its rule."""
        ungated = (
            analysis.credential_accepting
            - analysis.gated
            - CREDENTIAL_ROUTES_INTENTIONALLY_UNLIMITED
        )
        assert not ungated, (
            "credential-accepting routes with no rate limit: "
            + ", ".join(
                f"{name} ({analysis.routes[name]['module']}{analysis.routes[name]['rule']})"
                for name in sorted(ungated)
            )
            + ". Add @ratelimit.rate_limited(...), or name the route in "
            "CREDENTIAL_ROUTES_INTENTIONALLY_UNLIMITED with the reason."
        )

    def test_the_exception_list_names_real_routes(self, analysis: _Analysis) -> None:
        """A stale exception silently re-opens the hole it documented."""
        unknown = CREDENTIAL_ROUTES_INTENTIONALLY_UNLIMITED - set(analysis.routes)
        assert not unknown, sorted(unknown)

    def test_the_exception_list_is_currently_empty(self) -> None:
        """Named so a future addition is a deliberate, reviewed diff, not drift."""
        assert CREDENTIAL_ROUTES_INTENTIONALLY_UNLIMITED == frozenset()

    def test_a_safe_route_is_correctly_left_out(self, analysis: _Analysis) -> None:
        """The predicate must not over-match, or the guard proves nothing.

        `get_backup_codes` (GET, auth_required, reads stored codes) checks
        no secret and creates no side effect -- it must NOT appear in the
        credential-accepting set.
        """
        assert "get_backup_codes" not in analysis.credential_accepting

    def test_logout_is_correctly_left_out(self, analysis: _Analysis) -> None:
        """`logout` is authenticated and revokes tokens -- no secret is verified."""
        assert "logout" not in analysis.credential_accepting
