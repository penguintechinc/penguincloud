"""The browser and the portal must agree on the portal's OWN URLs.

Why this file exists
====================
``test_gough_webui_paths.py`` ties the two sides together for the
PRODUCT-relative fragment — the trailing slash that decides 308-vs-404 at
Gough. It does not, and cannot, say anything about the portal URL the webui
wraps that fragment in.

That gap shipped a defect. The browser built
``/api/v1/proxy/{id}/{path}`` while the portal registers
``/api/v1/products/{id}/proxy/{path}``, so every proxied product call —
all three Gough tables, its create/update/delete verbs, and the Elder and
SkausWatch overview cards — hit a route that does not exist. Both sides had
tests. The jest suite stripped the prefix with ``^/proxy/\\d+/``, a regex
transcribed from the broken value, so it agreed with it by construction.

The assertion below is deliberately NOT a transcription of the route. It
reads the rule out of Quart's live ``url_map`` and compares it to the
constant the TypeScript builds its URL from, so neither side is checked
against a copy of itself. Adding a ``url_prefix`` to ``proxy_bp``, renaming a
parameter, or editing the TS constant alone all turn this red.

The TypeScript is read as text on purpose, for the same reason
``test_gough_webui_paths.py`` does: importing it would need a JS runtime in
the Python suite, and parsing the literal keeps the assertion in the suite
that owns the route it is comparing against.

The same gap, one layer over
============================
Single-sourcing the PROXY url left the TYPED portal routes unguarded:
``nestResources.ts`` and ``goughOperations.ts`` hand-spelled ten URLs between
them (create, delete, action, four operation routes, metrics) and nothing tied
any of them to ``url_map``. A renamed path parameter or a ``url_prefix`` on
``operations_bp`` would have 404'd every write with nothing failing — the same
defect class, in the layer nobody had got to yet.

``PORTAL_TYPED_RULES`` in ``portalPaths.ts`` now maps each rule to the Quart
ENDPOINT that serves it, and :class:`TestTypedRoutes` below resolves every one
against the live ``url_map``. Naming the endpoint is what makes it
unfakeable: a rule pointing at nothing fails on the lookup, before any string
comparison happens.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest
from quart import Quart

#: Repo root, resolved from this file so the test does not depend on cwd.
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

_PORTAL_PATHS_TS: Final[Path] = (
    _REPO_ROOT
    / "services"
    / "webui"
    / "src"
    / "client"
    / "api"
    / "portalPaths.ts"
)

#: ``<int:connection_id>`` / ``<path:proxy_path>`` / ``<kind>`` → ``{name}``.
_WERKZEUG_PARAM_RE: Final[re.Pattern[str]] = re.compile(r"<(?:[^:>]+:)?([^>]+)>")


def _ts_const(name: str) -> str:
    """Read one exported string constant out of ``portalPaths.ts``."""
    source = _PORTAL_PATHS_TS.read_text(encoding="utf-8")
    match = re.search(
        rf"export const {name}\s*=\s*\n?\s*\"(?P<value>[^\"]+)\"", source
    )
    assert match is not None, (
        f"export const {name} not found in {_PORTAL_PATHS_TS}. If it was "
        f"renamed or restructured, update this parser — do not delete the "
        f"assertion, it is the only thing tying the two sides together."
    )
    return match.group("value")


#: ``"<rule>": "<endpoint>",`` inside the ``PORTAL_TYPED_RULES`` object, whose
#: keys are quoted paths (unlike the identifier keys of a normal TS object) and
#: whose values may sit on the following line once Prettier wraps them.
_TYPED_RULE_RE: Final[re.Pattern[str]] = re.compile(
    r'"(?P<rule>/api/[^"]+)":\s*\n?\s*"(?P<endpoint>[a-z_]+\.[a-z_]+)"',
)

#: Path of the generated OpenAPI types, whose path keys are a third copy of
#: the same strings — derived from ``openapi/v1.yaml`` rather than written.
_SCHEMA_D_TS: Final[Path] = (
    _REPO_ROOT / "services" / "webui" / "src" / "client" / "api" / "schema.d.ts"
)

#: Everything the ban rule below walks. The whole client tree, not just
#: ``api/`` — a page or hook can call ``api.get`` directly, and the point is
#: that nothing anywhere spells a portal URL for itself.
_WEBUI_SRC: Final[Path] = _REPO_ROOT / "services" / "webui" / "src" / "client"

#: An axios call whose URL is a literal beginning ``/products``.
#:
#: Matched on the CALL rather than on the bare string, because a portal API URL
#: and a browser route are indistinguishable as strings — ``/products/gough/
#: nodes`` is a router path in ``App.tsx`` and ``navigate()`` call sites, and a
#: rule that only looked at the literal would demand a ``portalUrl`` builder for
#: every one of them. Keying on ``api.<verb>(`` excludes those structurally,
#: which is better than exempting files by name and hoping the list stays right.
#:
#: ``["'`]`` covers double, single AND template quoting. The first version of
#: this rule saw only the backtick form, under ``api/*.ts`` only — which is how
#: three quoted literals in ``products.ts`` sat unguarded beside the guard
#: written for that file.
#: Prefixes whose call sites must go through a ``portalUrl`` builder. Grown
#: from ``/products`` alone: the ``/tenants`` and ``/dashboard`` groups were
#: named as a known gap in round 2, and the one dead route found that round
#: (``/dashboard/rollup``) came out of exactly that group — so the gap was the
#: same unguarded class, not a smaller one.
_GUARDED_PREFIXES: Final[tuple[str, ...]] = (
    "products",
    "tenants",
    "dashboard",
    "users/me",
)

_PORTAL_URL_LITERAL_RE: Final[re.Pattern[str]] = re.compile(
    r"""\bapi\.(?:get|post|put|patch|delete|request)\(\s*["'`]"""
    r"""(/(?:""" + "|".join(_GUARDED_PREFIXES) + r""")(?:[/"'`]|\$))""",
)

#: ANY literal URL handed to an axios verb, whatever its prefix. Used by the
#: resolution check, which is a superset of the ban rule: a literal outside
#: ``_GUARDED_PREFIXES`` is still allowed to BE a literal, but it must still
#: name a route the portal registers.
_ANY_API_LITERAL_RE: Final[re.Pattern[str]] = re.compile(
    r"""\bapi\.(?P<verb>get|post|put|patch|delete)\(\s*["'`](?P<path>/[^"'`]*)["'`]""",
)

#: ``${expr}`` in a template literal — a parameter, whatever it is named.
_TS_INTERP_RE: Final[re.Pattern[str]] = re.compile(r"\$\{[^}]+\}")

#: Methods Werkzeug synthesises; never what a handler declares.
_IMPLICIT_METHODS: Final[frozenset[str]] = frozenset({"HEAD", "OPTIONS"})


def _client_sources() -> list[tuple[Path, str]]:
    """Every non-test client source, as ``(path, text)``.

    Tests are excluded because a fixture URL is a deliberate stand-in — a test
    asserting a 404 path is not a defect. Nothing else is excluded: a page or a
    store can call ``api.get`` directly, and both did.
    """
    files = sorted(_WEBUI_SRC.rglob("*.ts")) + sorted(_WEBUI_SRC.rglob("*.tsx"))
    return [
        (path, path.read_text(encoding="utf-8"))
        for path in files
        if "__tests__" not in path.parts and "tests" not in path.parts
    ]


def _typed_rules() -> dict[str, str]:
    """Parse ``PORTAL_TYPED_RULES`` (rule → Quart endpoint) from the TS."""
    source = _PORTAL_PATHS_TS.read_text(encoding="utf-8")
    match = re.search(
        r"export const PORTAL_TYPED_RULES\s*=\s*\{(?P<body>.*?)\}\s*as const;",
        source,
        re.DOTALL,
    )
    assert match is not None, (
        f"PORTAL_TYPED_RULES not found in {_PORTAL_PATHS_TS}. If it was "
        f"renamed or restructured, update this parser — do not delete the "
        f"assertion, it is the only thing tying the typed routes together."
    )
    rules = {
        entry.group("rule"): entry.group("endpoint")
        for entry in _TYPED_RULE_RE.finditer(match.group("body"))
    }
    assert rules, "parsed PORTAL_TYPED_RULES but found no entries"
    return rules


#: One ``name: (args) => \`/path\`,`` entry of the ``portalUrl`` object. The body
#: is either a template literal or a plain quoted string (``products``,
#: ``productTypes``), so both quote styles are accepted.
_BUILDER_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s{2}(?P<name>[a-zA-Z]+):\s*\([^)]*\):\s*string\s*=>\s*\n?\s*"
    r"[`\"'](?P<path>/[^`\"']*)[`\"']",
    re.MULTILINE,
)


def _shape(path: str) -> str:
    """Reduce a path to its structure: literals kept, parameters flattened.

    ``/products/${productId}/health`` and ``/api/v1/products/{product_id}/health``
    both become ``/products/{}/health`` (after the base prefix is stripped), so
    a builder and a rule can be compared without caring what either side named
    its parameter.
    """
    collapsed = re.sub(r"\$\{[^}]+\}", "{}", path)
    return re.sub(r"\{[^}]+\}", "{}", collapsed)


def _builder_shapes() -> dict[str, str]:
    """Parse ``portalUrl`` into ``{builder name: path shape}``."""
    source = _PORTAL_PATHS_TS.read_text(encoding="utf-8")
    match = re.search(
        r"export const portalUrl\s*=\s*\{(?P<body>.*?)\n\}\s*as const;",
        source,
        re.DOTALL,
    )
    assert match is not None, (
        f"portalUrl object not found in {_PORTAL_PATHS_TS} — update this "
        f"parser rather than deleting the assertion it feeds."
    )
    builders = {
        entry.group("name"): _shape(entry.group("path"))
        for entry in _BUILDER_RE.finditer(match.group("body"))
    }
    assert builders, "parsed portalUrl but found no builders"
    return builders


def _declared_methods_by_shape(app: Quart) -> dict[str, set[str]]:
    """``{path shape: declared methods}`` from the live ``url_map``.

    ``rule.methods`` is ``set[str] | None`` in Werkzeug's typing, so the
    ``None`` case is handled once here rather than at each call site — a
    ``or set()`` scattered through two tests is how one of them ends up
    comparing against nothing.
    """
    shapes: dict[str, set[str]] = {}
    for rule in app.url_map.iter_rules():
        shape = _shape(_WERKZEUG_PARAM_RE.sub(r"{\1}", str(rule)))
        declared = (rule.methods or set()) - _IMPLICIT_METHODS
        shapes.setdefault(shape, set()).update(declared)
    return shapes


def _rule_for(app: Quart, endpoint: str) -> str:
    """The registered rule for one endpoint, in OpenAPI placeholder syntax."""
    for rule in app.url_map.iter_rules():
        if rule.endpoint == endpoint:
            return _WERKZEUG_PARAM_RE.sub(r"{\1}", str(rule))
    pytest.fail(f"the portal registers no endpoint named {endpoint!r}")


def test_portal_paths_file_exists() -> None:
    """The shared constant must be where the guard expects it."""
    assert _PORTAL_PATHS_TS.is_file(), f"missing {_PORTAL_PATHS_TS}"


@pytest.mark.asyncio
async def test_webui_proxy_rule_matches_the_registered_route(app: Quart) -> None:
    """The URL the browser builds must be the route the portal serves.

    Compared against the live ``url_map`` rather than a literal, so a
    ``url_prefix`` change on ``proxy_bp`` fails here instead of at runtime.
    """
    assert _ts_const("PORTAL_PROXY_RULE") == _rule_for(app, "proxy.proxy_request")


@pytest.mark.asyncio
async def test_webui_base_path_prefixes_the_proxy_rule(app: Quart) -> None:
    """The axios baseURL must be a prefix of the rule, not a second opinion.

    ``proxyRequestUrl`` returns a baseURL-relative path, so if these two drift
    apart the browser sends ``/api/v1/api/v1/...`` — a 404 that reads as a
    routing bug rather than a client one.
    """
    base = _ts_const("API_BASE_PATH")

    assert _rule_for(app, "proxy.proxy_request").startswith(f"{base}/")


@pytest.mark.asyncio
class TestTypedRoutes:
    """Every typed portal URL the browser builds must be a route Quart serves."""

    @pytest.mark.parametrize("rule", sorted(_typed_rules()))
    async def test_typed_rule_matches_the_registered_route(
        self, rule: str, app: Quart
    ) -> None:
        """Resolved through the Quart ENDPOINT, not compared to a literal.

        A rule naming an endpoint the portal does not register fails in
        ``_rule_for`` before any comparison, so this cannot be satisfied by a
        pair of strings that agree with each other and with nothing else.
        """
        assert rule == _rule_for(app, _typed_rules()[rule])

    async def test_every_typed_rule_starts_at_the_axios_base_path(
        self, app: Quart
    ) -> None:
        """The builders return baseURL-relative paths; the rules are absolute.

        If a rule did not start with the base path the two could never agree,
        and the mismatch would surface as ``/api/v1/api/v1/...`` at runtime.
        """
        base = _ts_const("API_BASE_PATH")

        for rule in _typed_rules():
            assert rule.startswith(f"{base}/"), rule

    async def test_the_call_sites_spell_no_portal_url_of_their_own(self) -> None:
        """No module may build a portal API URL outside portalPaths.ts.

        This is the assertion that makes the guard above cover the CODE rather
        than just a table beside it. ``nestResources.ts`` and
        ``goughOperations.ts`` previously hand-spelled ten URLs; a new one
        added tomorrow would be equally unguarded, and the table would stay
        green while the call site 404s.

        The first version of this check was narrower than it read: ``.ts`` only
        (not ``.tsx``), only under ``api/``, and only backtick-prefixed. It
        therefore missed every QUOTED literal — including three in the very
        file it was written for (``products.ts`` — ``"/products/types"`` and
        two ``"/products"``), none of which were in ``PORTAL_TYPED_RULES``, so
        a ``url_prefix`` on ``products_bp`` would have broken them silently.
        Widening it found a fourth: ``dashboard.ts`` called
        ``"/dashboard/rollup"``, a route the portal does not register at all
        (the rule is ``/api/v1/tenants/{tenant_id}/dashboard/rollup``).

        **Known gap, deliberately not ratcheted here.** The rule's subject is
        ``/products``. The ``/tenants/*`` and ``/dashboard/*`` API call sites
        (``tenants.ts``, ``dashboard.ts``, ``stores/tenantStore.ts`` — 20 of
        them) are still literals and are NOT covered. Migrating them is a
        change of its own, and encoding them as an allowlist here would be a
        ratchet that hides them; they are named in the report instead.
        """
        offenders: list[str] = []
        for path, text in _client_sources():
            if path == _PORTAL_PATHS_TS:
                continue
            for match in _PORTAL_URL_LITERAL_RE.finditer(text):
                number = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(_REPO_ROOT)}:{number}")

        assert not offenders, (
            f"portal URLs spelled outside portalPaths.ts: {offenders}. Add a "
            f"builder to `portalUrl` and an entry to PORTAL_TYPED_RULES so the "
            f"url_map guard covers it."
        )

    async def test_every_builder_has_a_rule_backing_it(self) -> None:
        """Both halves of the pair, or the guard has a hole.

        The ban rule forces call sites through a ``portalUrl`` builder, and the
        rule test resolves each ``PORTAL_TYPED_RULES`` entry against
        ``url_map``. Neither notices a builder with NO rule — deleting a rule
        entry leaves its builder still in use, still hand-written, and no
        longer checked against the route it targets. Verified by removing
        ``/api/v1/products`` and watching this go red; without it, nothing did.
        """
        base = _ts_const("API_BASE_PATH")
        rule_shapes = {
            _shape(rule[len(base):]) for rule in _typed_rules()
        }

        unbacked = {
            name: shape
            for name, shape in _builder_shapes().items()
            if shape not in rule_shapes
        }

        assert not unbacked, (
            f"portalUrl builders with no PORTAL_TYPED_RULES entry: {unbacked}. "
            f"Every builder must name a rule, or the URL it produces is never "
            f"compared against the route it targets."
        )

    async def test_the_builder_parser_sees_them_all(self) -> None:
        """The check above is a set difference — an empty left side passes it.

        A parser that silently matched nothing would report zero unbacked
        builders forever, which is the failure mode this whole file exists to
        end. Named builders are asserted so a regex change that stops matching
        the template-literal form (or the plain-string form) fails here.
        """
        builders = _builder_shapes()

        assert {"products", "productTypes", "product", "resourceAction"} <= set(
            builders
        ), sorted(builders)
        assert builders["products"] == "/products"
        assert builders["product"] == "/products/{}"
        assert builders["resourceAction"] == "/products/{}/resources/{}/{}/actions/{}"

    async def test_every_literal_api_url_resolves_to_a_registered_route(
        self, app: Quart
    ) -> None:
        """The finder. Every literal URL, every prefix, method included.

        The ban rule only covers ``_GUARDED_PREFIXES``; this covers ALL of
        them, because a literal outside those groups is still allowed to be a
        literal but is not allowed to name a route that does not exist. It is
        the check that does the finding rather than the enforcing, and it has
        found one dead route per round it has been widened:

        * round 2 — ``/dashboard/rollup``, with a ``tenant_id`` query
          parameter. The rule is ``/api/v1/tenants/{tenant_id}/dashboard/
          rollup``; the provider rollup matrix had never worked.
        * round 3 — ``PUT /auth/me``. The auth blueprint serves GET only
          (``auth.get_me``), so saving a profile was a 405. The writable
          profile is ``PUT /users/me`` plus ``PUT /users/me/password``.
        * round 3 — ``/go/status``, ``/go/numa/info``, ``/go/memory/stats``,
          removed rather than repaired (see ``platform.ts``).

        **The method is checked, not just the path.** ``PUT /auth/me`` matched
        a real rule and would have passed a path-only comparison; it is a 405
        that no amount of path correctness catches.
        """
        rules = _declared_methods_by_shape(app)

        base = _ts_const("API_BASE_PATH")
        unresolved: list[str] = []
        checked = 0
        for path, text in _client_sources():
            for match in _ANY_API_LITERAL_RE.finditer(text):
                verb = match.group("verb").upper()
                raw = match.group("path")
                line = text.count("\n", 0, match.start()) + 1
                where = f"{path.relative_to(_REPO_ROOT)}:{line}"
                shape = _shape(f"{base}{_TS_INTERP_RE.sub('{}', raw)}")
                checked += 1
                if shape not in rules:
                    unresolved.append(
                        f"{where}  {verb} {raw} -> {shape}  NO SUCH ROUTE"
                    )
                elif verb not in rules[shape]:
                    unresolved.append(
                        f"{where}  {verb} {raw} -> {shape}  405, serves "
                        f"{sorted(rules[shape])}"
                    )

        assert checked > 0, (
            "found no literal api.* call sites at all — the matcher has "
            "stopped working and this check is passing vacuously"
        )
        assert not unresolved, (
            "webui calls URLs the portal does not serve:\n  "
            + "\n  ".join(unresolved)
            + "\n\nFix the call site, or say plainly that the route should "
            "exist and does not — do not bend the caller to a path that is "
            "merely nearby."
        )

    async def test_the_resolution_check_can_see_a_wrong_method(
        self, app: Quart
    ) -> None:
        """Falsifies the method half, which is the half that found the 405.

        A path-only comparison would have passed ``PUT /auth/me`` — the rule
        exists, it just does not serve PUT. Asserted directly so a future
        simplification to path-only equality fails here instead of silently
        halving the check.
        """
        rules = _declared_methods_by_shape(app)

        assert "/api/v1/auth/me" in rules, "auth.get_me is gone; update this test"
        assert rules["/api/v1/auth/me"] == {"GET"}, (
            "auth/me now serves more than GET — if PUT was added, Profile.tsx "
            "could go back to one call, but check the password split first"
        )
        assert "/api/v1/users/me" in rules
        assert "PUT" in rules["/api/v1/users/me"]
        assert "PUT" in rules["/api/v1/users/me/password"]

    async def test_the_ban_rule_can_see_every_quote_style(self) -> None:
        """Falsifies the matcher itself — it is a negative assertion.

        A check of the form "no file contains X" passes just as well when the
        pattern matches nothing at all, and the original version very nearly
        did: backticks only, ``api/*.ts`` only. These are the spellings it must
        catch, and the ones it must not.
        """
        for line in (
            '    const r = await api.get("/products/types");',
            "    const r = await api.get('/products');",
            "    const r = await api.get(`/products/${id}/health`);",
            '    await api.delete("/products/1");',
            "    const r = await api.post(`/products/${id}/test`);",
        ):
            assert _PORTAL_URL_LITERAL_RE.search(line), line

        for line in (
            '  <Route path="/products/gough/nodes" element={<NodesPage />} />',
            '  { name: "Nodes", href: "/products/gough/nodes", icon: Gauge },',
            '    navigate(`/products/${product.id}`);',
            "    const r = await api.get(portalUrl.products());",
        ):
            assert not _PORTAL_URL_LITERAL_RE.search(line), (
                f"{line!r} is a browser route or an already-built URL — the "
                f"matcher must not demand a portalUrl builder for it"
            )

    async def test_every_typed_rule_is_a_documented_openapi_path(self) -> None:
        """The generated spec types are a third, independent copy of the text.

        ``schema.d.ts`` is generated from ``openapi/v1.yaml``, so a rule
        absent from it is a route the portal serves and the spec does not
        document — which is also a spec bug, not only a naming one.
        """
        schema = _SCHEMA_D_TS.read_text(encoding="utf-8")

        missing = [rule for rule in _typed_rules() if f'"{rule}"' not in schema]

        assert not missing, (
            f"typed portal routes missing from the generated OpenAPI types: "
            f"{missing}. Regenerate schema.d.ts, or document the route in "
            f"openapi/v1.yaml if it is genuinely undocumented."
        )
