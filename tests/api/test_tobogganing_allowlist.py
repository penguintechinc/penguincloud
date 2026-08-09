"""Grade Tobogganing's proxy allowlist against Tobogganing's own route table.

Every path assertion here is bound to the product rather than to a
transcription: the route table and the per-route auth class come from a live
boot of Tobogganing (or the vendored copy of one in
``tests/api/fixtures/tobogganing_source.json``), never from this file.

The deny cases come first and each names its hazard, because an allowlist test
that only checks happy paths passes just as well against ``^/``.

The guard this module exists for
================================
Tobogganing has two auth planes and the portal holds a credential for only one.
``@require_machine_jwt`` rejects any token whose ``aud`` is not ``"headend"``
(``hub_api/auth/middleware.py:516-517``), while a portal connection's credential
comes from ``POST /api/v1/auth/login`` and carries ``aud="tobogganing"``
(``hub_api/auth/service.py:341``). A rule admitting a machine-plane route is
therefore a **guaranteed 401 that looks like a working feature** — and three of
the five resources Task 4T's brief named live entirely on that plane.

:func:`test_no_rule_admits_a_route_the_portal_cannot_authenticate` is the
mechanical version of that finding. It reads the auth class of every route out
of the product and fails if any allowlist rule matches a non-``user`` one, so
the claim survives Tobogganing changing a decorator — which prose in a docstring
would not.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

from app.adapters.base import ID_UUID
from app.adapters.tobogganing import (
    TOBOGGANING_ROUTE_ALLOWLIST,
    TOBOGGANING_UNEXPOSED_ROUTES,
)
from app.adapters.tobogganing.routes import (
    HEALTH_ENDPOINT,
    PATH_BLOCKPAGE_PAGES,
    PATH_BLOCKPAGE_ROUTES,
    PATH_CLUSTERS_FLAT,
    PATH_SDWAN_CLIENTS,
    PATH_SDWAN_CLUSTERS,
    PATH_SWG_CATEGORIES,
    PATH_SWG_POLICY,
    READY_ENDPOINT,
    SCOPE_MANAGE,
    SCOPE_READ,
    SEGMENT_PREVIEW,
    SEGMENT_PUBLISH,
)

from tobogganing_route_source import (
    AUTH_USER_JWT,
    effective_auth_table,
    effective_route_table,
    machine_only_paths,
)

#: A concrete uuid for exercising an id slot. Matches :data:`ID_UUID`.
_UUID: Final[str] = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"

#: Repo root, resolved from this file so the test does not depend on cwd.
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

#: The webui module whose ``proxyApi.request`` call sites are the browser-side
#: consumers of this allowlist.
_WEBUI_API_TS: Final[Path] = (
    _REPO_ROOT
    / "services"
    / "webui"
    / "src"
    / "client"
    / "api"
    / "resources"
    / "tobogganing.ts"
)

#: ``proxyApi.request(productId, "VERB", <path expression>`` — the verb and the
#: path expression, however Prettier has wrapped the arguments.
_PROXY_CALL_RE: Final[re.Pattern[str]] = re.compile(
    r"proxyApi\.request\(\s*productId,\s*\"(?P<verb>[A-Z]+)\",\s*"
    # An identifier, optionally followed by ONE subscript or argument list.
    # Stopping at the first comma would truncate
    # `blockPagePath(pageId, BLOCK_PAGE_SEGMENT_PREVIEW)` to `blockPagePath(pageId`,
    # which the resolver would then reject as unknown — a parser that fails
    # loudly, but on the wrong thing.
    r"(?P<expr>[A-Za-z_][\w.]*(?:\[[^\]]*\]|\([^)]*\))?)",
)


def _webui_collection_paths() -> dict[str, str]:
    """Parse ``TOBOGGANING_COLLECTION_PATHS`` out of the webui constant file.

    Duplicated deliberately from ``test_tobogganing_webui_paths.py`` rather
    than imported: that module asserts these values EQUAL the adapter's, so
    importing its parser here would make this check depend on the assertion it
    is meant to be independent of.
    """
    source = (_WEBUI_API_TS.parent / "tobogganingPaths.ts").read_text(encoding="utf-8")
    match = re.search(
        r"export const TOBOGGANING_COLLECTION_PATHS\s*=\s*\{(?P<body>.*?)\}"
        r"\s*as const;",
        source,
        re.DOTALL,
    )
    assert match is not None, "TOBOGGANING_COLLECTION_PATHS not found"
    entries = dict(re.findall(r'(\w+)\s*:\s*"([^"]+)"', match.group("body")))
    assert entries, "parsed TOBOGGANING_COLLECTION_PATHS but found no entries"
    return entries


def _matches(method: str, path: str) -> bool:
    """Whether any allowlist rule admits this exact request."""
    return any(rule.matches(method, path) for rule in TOBOGGANING_ROUTE_ALLOWLIST)


def _concrete(pattern: str) -> str:
    """Turn a rule's path regex back into one concrete path it admits.

    Only the shapes this adapter actually uses are substituted; anything else
    would silently produce a path the rule does not match and make a caller's
    assertion vacuous, so it raises instead.
    """
    path = pattern
    if path.startswith("^"):
        path = path[1:]
    if path.endswith(r"\Z"):
        path = path[: -len(r"\Z")]
    path = path.replace(ID_UUID, _UUID)
    if re.search(r"[\[\]\\+*?()|]", path.replace(r"\-", "-")):
        raise AssertionError(
            f"rule pattern {pattern!r} contains regex syntax this helper does "
            f"not know how to make concrete — extend it rather than skipping, "
            f"or every assertion about this rule is vacuous"
        )
    return path


class TestDenials:
    """What the allowlist must refuse, and the hazard each case names."""

    @pytest.mark.parametrize(
        ("method", "path", "hazard"),
        [
            (
                "GET",
                "/api/v1/firewall/rules",
                "machine plane (aud==headend) — a portal token can never "
                "satisfy it, and it exports every user's firewall rules",
            ),
            (
                "GET",
                "/api/v1/wireguard/peers",
                "machine plane — same NAME as the user-plane peers route but a "
                "different path; admitting it would look correct in review",
            ),
            (
                "GET",
                "/api/v1/headend/headend-1/ports",
                "machine plane — headend port topology",
            ),
            (
                "POST",
                "/api/v1/certs/certificates",
                "machine plane — issues X.509 certificates",
            ),
            (
                "GET",
                "/api/v1/sase/swg/radix",
                "machine plane — bulk policy tree export",
            ),
            (
                "POST",
                "/api/v1/sdwan/clients",
                "node enrolment — RETURNS a freshly minted api_key in the body",
            ),
            (
                "POST",
                "/api/v1/sdwan/clusters",
                "node enrolment — RETURNS a freshly minted api_key in the body",
            ),
            (
                "POST",
                "/api/v1/sdwan/clients/client-1/rotate-key",
                "node credential rotation — mints a replacement api_key",
            ),
            (
                "POST",
                "/api/v1/auth/login",
                "credential surface — never proxied",
            ),
            (
                "POST",
                "/api/v1/auth/token",
                "credential surface — mints machine JWTs",
            ),
            (
                "POST",
                "/api/v1/jwt/revoke",
                "credential surface — token revocation",
            ),
            (
                "GET",
                "/api/v1/auth/public-key",
                "signing-key surface",
            ),
            (
                "GET",
                "/openapi.json",
                "the API map itself — hands an attacker the enumeration step",
            ),
            (
                "GET",
                "/docs/public",
                "the API map itself",
            ),
            (
                "GET",
                "/api/v1/sdwan/status",
                "unauthenticated AND hardcodes tenant_id='default' "
                "(status.py:30) — proxying it leaks the default tenant's fleet "
                "counts into every other tenant's portal",
            ),
            (
                "GET",
                "/api/v1/netsvcs/zones",
                "a real user-plane route this adapter deliberately does not "
                "expose — deny-by-default must hold for reachable routes too, "
                "not only dangerous ones",
            ),
            (
                "DELETE",
                "/api/v1/sase/blockpages/pages/" + _UUID,
                "method not registered by the product; the PUT rule must not "
                "admit a DELETE at the same path",
            ),
            (
                "GET",
                "/api/v1/sdwan/clusters/",
                "trailing slash the product does NOT register here — a flat "
                "404 with no redirect back, which surfaces as an empty table",
            ),
            (
                "GET",
                "/api/v1/clusters",
                "MISSING the trailing slash the product DOES register here — "
                "a 308 the transport does not follow",
            ),
        ],
    )
    def test_rule_is_refused(self, method: str, path: str, hazard: str) -> None:
        """Each denial names the hazard it protects against."""
        assert not _matches(method, path), f"{method} {path} must be refused: {hazard}"

    def test_no_rule_admits_a_route_the_portal_cannot_authenticate(self) -> None:
        """THE guard: no rule may point at a non-user-plane route.

        Graded by the product itself — the auth class of every route is read
        out of a live boot (or the vendored copy), so this keeps holding when
        Tobogganing moves a route between planes. That is the difference
        between a check and a comment.
        """
        offenders = []
        for entry in sorted(machine_only_paths()):
            method, _, path = entry.partition(" ")
            # Substitute a concrete value for the product's converter syntax so
            # the rule matcher sees a real path.
            concrete = re.sub(r"<[^>]+>", "probe-1", path)
            if _matches(method, concrete):
                offenders.append(f"{method} {concrete}")

        assert not offenders, (
            f"these allowlist rules admit routes the portal's credential can "
            f"NEVER satisfy (machine-JWT aud=='headend', or an inline node "
            f"credential): {offenders}. Each would answer 401 while appearing "
            f"in the UI as a working feature."
        )

    def test_every_unexposed_route_is_actually_refused(self) -> None:
        """The declaration and the allowlist must agree.

        ``unexposed_routes`` is a claim; this is what makes it enforced.
        """
        for method, path in TOBOGGANING_UNEXPOSED_ROUTES:
            assert not _matches(
                method, path
            ), f"{method} {path} is declared unexposed but the allowlist admits it"


class TestAdmissions:
    """What the allowlist must admit — and that the product really serves it."""

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("GET", "/health"),
            ("GET", "/ready"),
            ("GET", "/api/v1/sdwan/clients"),
            ("GET", "/api/v1/sdwan/clusters"),
            ("GET", "/api/v1/sdwan/wireguard/peers"),
            ("GET", "/api/v1/sase/blockpages/pages"),
            ("GET", "/api/v1/sase/blockpages/routes"),
            ("GET", "/api/v1/sase/swg/policy"),
            ("POST", "/api/v1/sase/blockpages/pages"),
            ("PUT", "/api/v1/sase/blockpages/pages/" + _UUID),
            ("POST", "/api/v1/sase/blockpages/pages/" + _UUID + "/preview"),
            ("POST", "/api/v1/sase/blockpages/pages/" + _UUID + "/publish"),
            ("PUT", "/api/v1/sase/swg/policy"),
        ],
    )
    def test_rule_is_admitted(self, method: str, path: str) -> None:
        """Admission alone is not enough — see the route-existence test."""
        assert _matches(method, path), f"{method} {path} should be admitted"

    def test_every_rule_points_at_a_route_the_product_registers(self) -> None:
        """Phantom-route guard: a rule for a path Tobogganing does not serve.

        This is what caught Gough's advertised-but-unregistered endpoints in
        4G. Graded against the product's real ``url_map``, converter syntax
        normalised on both sides.
        """
        table = effective_route_table()
        registered = {
            (re.sub(r"<[^>]+>", "{id}", path), method)
            for path, methods in table.items()
            for method in methods
        }

        missing = []
        for rule in TOBOGGANING_ROUTE_ALLOWLIST:
            concrete = _concrete(rule.path_regex)
            normalised = concrete.replace(_UUID, "{id}")
            if (normalised, rule.method.upper()) not in registered:
                missing.append(f"{rule.method} {concrete}")

        assert not missing, (
            f"these allowlist rules point at routes Tobogganing does not "
            f"register: {missing}. A screen built on one answers 404 with an "
            f"empty table rather than an error."
        )

    def test_every_admitted_route_is_on_the_user_plane(self) -> None:
        """Positive form of the machine-plane guard.

        The negative test proves no rule reaches a machine route; this proves
        every rule reaches a *user* one, so a route with an unrecognised auth
        class cannot slip through the gap between the two.
        """
        auth = effective_auth_table()
        wrong = []
        for rule in TOBOGGANING_ROUTE_ALLOWLIST:
            concrete = _concrete(rule.path_regex)
            if concrete in ("/health", "/ready"):
                continue  # genuinely public liveness
            normalised = re.sub(re.escape(_UUID), "<page_id>", concrete)
            kind = auth.get(f"{rule.method.upper()} {normalised}")
            if kind is not None and kind != AUTH_USER_JWT:
                wrong.append(f"{rule.method} {normalised} is {kind!r}")

        assert not wrong, (
            f"these allowlist rules point at routes that are not on the user "
            f"plane: {wrong}"
        )


class TestStructure:
    """Structural properties that must hold however the rules are edited."""

    def test_every_mutating_verb_requires_manage(self) -> None:
        """A read-only caller must never reach a destructive route."""
        for rule in TOBOGGANING_ROUTE_ALLOWLIST:
            if rule.method.upper() in {"GET", "HEAD", "OPTIONS"}:
                continue
            assert rule.required_scope == SCOPE_MANAGE, (
                f"{rule.method} {rule.path_regex} is a mutating verb but "
                f"requires {rule.required_scope!r}"
            )

    def test_reads_require_the_narrow_read_scope(self) -> None:
        """Rules name the per-product scope, never the coarse one.

        The coarse ``products:read`` satisfies this one, so naming the narrow
        form costs nothing today and is what allows a narrower grant later.
        """
        for rule in TOBOGGANING_ROUTE_ALLOWLIST:
            if rule.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
                continue
            assert rule.required_scope == SCOPE_READ

    def test_the_two_cluster_paths_keep_their_opposite_slash_shapes(self) -> None:
        """Pin the asymmetry itself so a "tidy-up" to one shape fails here.

        The defect class is not a typo — it is the assumption that one slash
        convention covers a product. Tobogganing disproves it within a single
        API, so the disproof is stated as a test.
        """
        assert PATH_CLUSTERS_FLAT.endswith("/")
        assert not PATH_SDWAN_CLUSTERS.endswith("/")

        table = effective_route_table()
        assert PATH_CLUSTERS_FLAT in table, (
            "the product no longer registers the flat cluster list WITH a "
            "trailing slash — the adapter's path is now a 404"
        )
        assert PATH_SDWAN_CLUSTERS in table, (
            "the product no longer registers the sdwan cluster list WITHOUT a "
            "trailing slash — the adapter's path is now a 308"
        )

    def test_no_rule_admits_the_auth_namespace(self) -> None:
        """Blanket structural check, independent of the enumerated denials."""
        for rule in TOBOGGANING_ROUTE_ALLOWLIST:
            concrete = _concrete(rule.path_regex)
            assert not concrete.startswith("/api/v1/auth/")
            assert not concrete.startswith("/api/v1/jwt/")


class TestConsumers:
    """Every allowlist rule must have something that actually calls it.

    Deny-by-default answers "what MAY be reached". It says nothing about what
    IS reached, and the gap between them is reachable attack surface backing no
    feature. The first cut of this adapter carried three such rules — two of
    them MUTATING (``PUT /sase/blockpages/routes``, ``POST /sase/swg/categories``)
    plus ``GET /api/v1/clusters/`` — and they survived because the webui side
    pins "exactly the collections its screens fetch" while the allowlist had no
    equivalent. Review caught them; this makes the next three fail a build.

    The consumers span two languages, so the expected set is DERIVED from both
    rather than transcribed:

    * the adapter's ``_COLLECTIONS`` map (every entry is issued as a ``GET``),
    * the webui's ``proxyApi.request`` call sites, parsed out of
      ``tobogganing.ts`` and resolved against the constants in
      ``tobogganingPaths.ts``.

    A rule may legitimately precede its screen — that is not forbidden, it just
    has to be stated. :data:`_UNCONSUMED_BY_DESIGN` is the place to state it,
    and it is deliberately awkward to add to: each entry needs a reason, and
    the test asserts the entry is still unconsumed, so a stale exemption fails
    rather than quietly widening the surface.
    """

    #: Rules with no code consumer, each with the reason it stays.
    #:
    #: Liveness probes only. They are reached by operators and diagnostics
    #: rather than by a typed method, are non-mutating, and Nest's adapter
    #: carries the identical pair — so removing them here would diverge from
    #: the sibling adapter rather than close a hole.
    _UNCONSUMED_BY_DESIGN: Final[dict[tuple[str, str], str]] = {
        ("GET", HEALTH_ENDPOINT): "liveness probe, reached by operators",
        ("GET", READY_ENDPOINT): "readiness probe, reached by operators",
    }

    @staticmethod
    def _adapter_consumers() -> set[tuple[str, str]]:
        """``GET`` on every collection the adapter lists."""
        from app.adapters.tobogganing.adapter import _COLLECTIONS

        return {("GET", path) for path in _COLLECTIONS.values()}

    @staticmethod
    def _webui_consumers() -> set[tuple[str, str]]:
        """Every ``proxyApi.request`` call site in ``tobogganing.ts``.

        Parsed rather than listed: a transcription would agree with itself
        while the call sites moved, which is the failure mode this whole file
        exists to prevent.
        """
        paths = _webui_collection_paths()
        source = _WEBUI_API_TS.read_text(encoding="utf-8")

        calls = _PROXY_CALL_RE.findall(source)
        assert calls, (
            f"parsed {_WEBUI_API_TS} and found no proxyApi.request calls — the "
            f"matcher has stopped working and this check is now vacuous"
        )

        consumers: set[tuple[str, str]] = set()
        for verb, expr in calls:
            expr = expr.strip()
            if expr == "TOBOGGANING_COLLECTION_PATHS[collection]":
                # The generic list() helper — reaches every collection.
                consumers.update((verb, f"/{p}") for p in paths.values())
                continue
            member = re.fullmatch(r"TOBOGGANING_COLLECTION_PATHS\.(\w+)", expr)
            if member:
                consumers.add((verb, f"/{paths[member.group(1)]}"))
                continue
            item = re.fullmatch(
                r"blockPagePath\(\s*pageId\s*(?:,\s*(?P<seg>\w+)\s*)?\)", expr
            )
            if item:
                base = f"/{paths['blockPages']}/{_UUID}"
                segment = item.group("seg")
                literal = (
                    {
                        "BLOCK_PAGE_SEGMENT_PREVIEW": SEGMENT_PREVIEW,
                        "BLOCK_PAGE_SEGMENT_PUBLISH": SEGMENT_PUBLISH,
                    }.get(segment)
                    if segment
                    else None
                )
                consumers.add((verb, f"{base}/{literal}" if literal else base))
                continue
            raise AssertionError(
                f"proxyApi.request path expression {expr!r} is one this parser "
                f"does not resolve — extend it rather than skipping, or the "
                f"rule it consumes will look unconsumed"
            )
        return consumers

    def test_every_rule_has_a_consumer(self) -> None:
        """No rule may admit a request nothing makes."""
        consumers = self._adapter_consumers() | self._webui_consumers()

        orphans = []
        for rule in TOBOGGANING_ROUTE_ALLOWLIST:
            concrete = _concrete(rule.path_regex)
            key = (rule.method.upper(), concrete)
            if key in self._UNCONSUMED_BY_DESIGN:
                continue
            if not any(rule.matches(method, path) for method, path in consumers):
                orphans.append(f"{rule.method} {concrete}")

        assert not orphans, (
            f"allowlist rules nothing calls: {orphans}. Remove them, or add "
            f"them to _UNCONSUMED_BY_DESIGN with the reason. A mutating rule "
            f"with no caller is reachable surface backing no feature."
        )

    def test_the_consumer_derivation_is_not_vacuous(self) -> None:
        """A set difference passes trivially when the right side is huge.

        If the parsers silently matched everything, every rule would look
        consumed forever. The counts and a few known members are pinned so a
        broken parser fails here instead of turning the check above green.
        """
        adapter = self._adapter_consumers()
        webui = self._webui_consumers()

        assert len(adapter) == 6, sorted(adapter)
        assert ("GET", PATH_SDWAN_CLIENTS) in adapter
        assert ("GET", PATH_BLOCKPAGE_ROUTES) in adapter

        # Reads via the generic helper, plus create/update/preview/publish/policy.
        assert ("GET", PATH_SDWAN_CLIENTS) in webui
        assert ("POST", PATH_BLOCKPAGE_PAGES) in webui
        assert ("PUT", PATH_SWG_POLICY) in webui
        assert ("POST", f"{PATH_BLOCKPAGE_PAGES}/{_UUID}/{SEGMENT_PUBLISH}") in webui
        assert ("PUT", f"{PATH_BLOCKPAGE_PAGES}/{_UUID}") in webui

    def test_no_exemption_is_stale(self) -> None:
        """An exemption that gained a consumer must be deleted, not kept.

        Otherwise the list grows into a permanent allowlist-of-the-allowlist
        and stops meaning anything.
        """
        consumers = self._adapter_consumers() | self._webui_consumers()

        for (method, path), reason in self._UNCONSUMED_BY_DESIGN.items():
            assert reason, f"{method} {path} is exempted with no reason"
            assert not any(
                rule.matches(m, p)
                for rule in TOBOGGANING_ROUTE_ALLOWLIST
                if rule.method.upper() == method and _concrete(rule.path_regex) == path
                for m, p in consumers
            ), f"{method} {path} now HAS a consumer — drop the exemption"

    def test_the_removed_rules_stay_removed(self) -> None:
        """The three fix-round-1 removals, named so they cannot drift back.

        All three are tenant-scoped upstream, so this was surface rather than a
        hole — but two of them are mutating verbs reachable through the proxy
        with nothing behind them, which is not a state to re-enter silently.
        """
        assert not _matches("GET", PATH_CLUSTERS_FLAT)
        assert not _matches("PUT", PATH_BLOCKPAGE_ROUTES)
        assert not _matches("POST", PATH_SWG_CATEGORIES)

        # The reads that share those paths must still be admitted.
        assert _matches("GET", PATH_BLOCKPAGE_ROUTES)
        assert _matches("GET", PATH_SDWAN_CLUSTERS)
