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
