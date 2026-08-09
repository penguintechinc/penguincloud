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
        """No module may build a ``/products/...`` URL outside portalPaths.ts.

        This is the assertion that makes the guard above cover the CODE rather
        than just a table beside it. ``nestResources.ts`` and
        ``goughOperations.ts`` previously hand-spelled ten URLs; a new one
        added tomorrow would be equally unguarded, and the table would stay
        green while the call site 404s.
        """
        api_dir = _PORTAL_PATHS_TS.parent
        offenders: list[str] = []
        for path in sorted(api_dir.rglob("*.ts")):
            if path == _PORTAL_PATHS_TS or "__tests__" in path.parts:
                continue
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if "`/products/" in line:
                    offenders.append(f"{path.relative_to(_REPO_ROOT)}:{number}")

        assert not offenders, (
            f"portal URLs spelled outside portalPaths.ts: {offenders}. Add a "
            f"builder to `portalUrl` and an entry to PORTAL_TYPED_RULES so the "
            f"url_map guard covers it."
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
