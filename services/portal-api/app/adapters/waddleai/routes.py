"""WaddleAI route shapes and the deny-by-default proxy allowlist.

Phase 8 acceptance test (design §8): a REPRESENTATIVE read-only subset —
``providers``, ``knowledge``, ``quotas`` — proving a fourth product onboards
through the adapter+manifest mechanism alone, with zero new webui/CLI code.
Not the whole WaddleAI surface; see the adapter module docstring for what
was deliberately left out and why.

Every path here is a LITERAL collection route with no variable id segment —
unlike Gough/Tobogganing, this adapter's allowlist has nothing for the
typed-id-shape machinery (:data:`~app.adapters.base.ID_INT` et al.) to type,
because :attr:`WADDLEAI_ROUTE_ALLOWLIST` proxies collections only, never an
item. That is also why :data:`WADDLEAI_UNEXPOSED_ROUTES` may stay empty:
``test_adapter_registry.py``'s ``test_an_adapter_with_id_patterns_must_declare_unexposed_routes``
only requires it non-empty when a rule contains a variable segment.

Verified against WaddleAI's real handler source
(``services/management/app/api/v1/{providers,knowledge,quotas}.py``,
``penguintechinc/waddleai`` on GitHub), not merely its OpenAPI spec — the
``knowledge`` and ``quotas`` response schemas are explicitly unannotated
there ("Response schema not yet annotated with @validate_response"), so the
spec alone cannot prove the wire shape. ``providers`` IS fully typed in the
spec (``ProviderListResponse``) and the handler source agrees with it byte
for byte.

Why no item route is allowlisted for any of the three
=======================================================
* ``GET /api/v1/providers/{id}`` is real (``ProviderDetailResponse``,
  ``providers.py``) but additionally returns ``extra_config``/``tls_config``/
  ``ailb_route_config`` — fields the list response deliberately omits. This
  manifest declares ``item_path=None`` for every resource (see
  ``manifest.py``) rather than allowlist a detail route whose extra fields
  have not been reviewed for this cut.
* ``GET /api/v1/knowledge/{doc_id}`` is real too, but adds nothing the list
  row does not already carry (``knowledge.py``'s ``_serialize`` is identical
  for both), so there is no detail-only field to justify a second route.
* WaddleAI has no ``GET /api/v1/quotas/{id}`` at all — the only per-entity
  read is ``GET /api/v1/quotas/status/{entity_id}``, which requires an
  ``entity_type`` disambiguator (``?type=key|user|org``) because quota rows
  are NOT uniquely identified by id alone (an org, a user and a key can all
  have id=1). Declaring an item route for ``quota`` would be dishonest about
  what the collection actually identifies.

Every read-only rule takes :data:`SCOPE_READ`, built with
:func:`~app.adapters.base.product_scope` per the model in
:mod:`app.adapters.base` ("Per-product scopes"). No mutating verb is
allowlisted at all — this is a read-only cut, and
``test_only_integrated_products_may_proxy_a_mutating_verb`` in
``test_adapter_registry.py`` enforces that registry-wide for any adapter not
on its own reviewed-write list, which WaddleAI is not.
"""

from __future__ import annotations

from typing import Final

from ..base import RouteRule, product_scope

__all__ = [
    "PRODUCT_TYPE",
    "SCOPE_READ",
    "SCOPE_MANAGE",
    "SCOPES",
    "API_PREFIX",
    "HEALTH_ENDPOINT",
    "PATH_PROVIDERS",
    "PATH_KNOWLEDGE",
    "PATH_QUOTAS",
    "WADDLEAI_ROUTE_ALLOWLIST",
    "WADDLEAI_UNEXPOSED_ROUTES",
]

#: Registry key. Must match ``ADAPTER_REGISTRY``.
PRODUCT_TYPE: Final[str] = "waddleai"

#: Per-product scopes — see "Per-product scopes" in :mod:`app.adapters.base`.
#: ``SCOPE_MANAGE`` is declared for symmetry with every other product module
#: (and because ``product_scope`` is a shared constructor, not a per-product
#: one) even though no rule below requires it — this cut proxies no write.
SCOPE_READ: Final[str] = product_scope(PRODUCT_TYPE, "read")
SCOPE_MANAGE: Final[str] = product_scope(PRODUCT_TYPE, "manage")
SCOPES: Final[tuple[str, str]] = (SCOPE_READ, SCOPE_MANAGE)

#: WaddleAI's management API mounts everything under this prefix
#: (``services/management/app/api/v1/__init__.py``).
API_PREFIX: Final[str] = "/api/v1"

#: WaddleAI registers ``/healthz`` at the app root
#: (``services/management/app/__init__.py``) — the same path
#: :class:`~app.adapters.base.HealthOnlyAdapter` already defaults to, spelled
#: out here for legibility rather than left implicit.
HEALTH_ENDPOINT: Final[str] = "/healthz"

#: Collection routes for the three resources this cut implements. Each is
#: read with no auth-plane ambiguity: WaddleAI has exactly one auth plane
#: (bearer JWT via ``require_auth``/``require_scope``), unlike Tobogganing's
#: user/machine split.
PATH_PROVIDERS: Final[str] = f"{API_PREFIX}/providers"
PATH_KNOWLEDGE: Final[str] = f"{API_PREFIX}/knowledge"
PATH_QUOTAS: Final[str] = f"{API_PREFIX}/quotas"

#: Deny-by-default proxy allowlist. GET-only, no variable id segment — see
#: the module docstring for why no item route is admitted for any kind.
WADDLEAI_ROUTE_ALLOWLIST: list[RouteRule] = [
    RouteRule("GET", rf"^{HEALTH_ENDPOINT}\Z", SCOPE_READ),
    RouteRule("GET", rf"^{PATH_PROVIDERS}\Z", SCOPE_READ),
    RouteRule("GET", rf"^{PATH_KNOWLEDGE}\Z", SCOPE_READ),
    RouteRule("GET", rf"^{PATH_QUOTAS}\Z", SCOPE_READ),
]

#: Empty is honest here, not lazy: every rule above is a literal path with no
#: variable segment for a sibling literal to collide with, so the hazard
#: :attr:`~app.adapters.base.Adapter.unexposed_routes` exists to close
#: structurally cannot arise in this allowlist. See
#: ``test_an_adapter_with_id_patterns_must_declare_unexposed_routes`` in
#: ``tests/api/test_adapter_registry.py``, which only requires a non-empty
#: declaration once a rule HAS a variable segment.
WADDLEAI_UNEXPOSED_ROUTES: tuple[tuple[str, str], ...] = ()
