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
from typing import Final

import pytest

from app.adapters.base import ID_UUID
from app.adapters.tobogganing import (
    TOBOGGANING_ROUTE_ALLOWLIST,
    TOBOGGANING_UNEXPOSED_ROUTES,
)
from app.adapters.tobogganing.routes import (
    PATH_CLUSTERS_FLAT,
    PATH_SDWAN_CLUSTERS,
    SCOPE_MANAGE,
    SCOPE_READ,
)

from tobogganing_route_source import (
    AUTH_USER_JWT,
    effective_auth_table,
    effective_route_table,
    machine_only_paths,
)

#: A concrete uuid for exercising an id slot. Matches :data:`ID_UUID`.
_UUID: Final[str] = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"


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
            ("GET", "/api/v1/clusters/"),
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
            ("PUT", "/api/v1/sase/blockpages/routes"),
            ("PUT", "/api/v1/sase/swg/policy"),
            ("POST", "/api/v1/sase/swg/categories"),
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
