"""Role-based scope enforcement — floor-level, importable from every layer.

:class:`RBACEnforcer` is the sole scope-matching primitive behind both the
portal's own routes (``app.authz.require_scope``) and the proxy's
``RouteRule`` allowlist (``app.proxy``). It used to live in
``app.adapters.base``, which put ``app.authz`` — foundational auth — in the
position of importing the proxy/adapters layer to reach a pure scope
comparison that has no adapter knowledge at all: :class:`RBACEnforcer` reads
only ``required``/``granted`` scope strings, never a ``RouteRule`` or an
``Adapter``. Moved here so every layer above the floor (auth, tenancy,
licensing, proxy, health, routes) can depend on it directly, instead of
routing that dependency sideways through the proxy layer.

This module must import nothing from ``app.adapters``, ``app.licensing``,
``app.tenancy``, or any route module — that is what makes it safe for
``app.authz`` to depend on without recreating the edge this module exists to
remove. See ``tests/architecture/test_layer_boundaries.py`` for the
mechanically enforced version of that constraint.
"""

from __future__ import annotations

from typing import Final

#: Namespace shared by the coarse and per-product product scopes
#: (``products:read`` / ``products:{type}:{action}``). A third copy of the
#: same literal, already duplicated between ``app.adapters.base`` and
#: ``app.tenancy.authz`` — see those two modules' own comments for why each
#: of them carries its own copy rather than importing the other. This one
#: exists for the identical reason: this module may import nothing above the
#: floor, so it cannot import either existing copy without recreating the
#: edge it was extracted to remove. All three are asserted equal in
#: ``tests/api/test_product_scopes.py``.
_PRODUCT_SCOPE_NAMESPACE: Final[str] = "products"


class RBACEnforcer:
    """Enforces role-based access control via scope matching.

    Shared between portal routes (@require_scope decorator) and proxy
    allowlist (RouteRule scope checks). Scopes are issued at token time
    and stored in the JWT; enforcement is zero-cost at request time.

    One implication is recognised, and only one: the coarse
    ``products:{action}`` scope satisfies the per-product
    ``products:{type}:{action}`` form. See "Per-product scopes" in
    :mod:`app.adapters.base`'s module docstring for why the relation lives
    here rather than being expanded at every call site.
    """

    def __init__(self, required_scopes: str | list[str]) -> None:
        """Initialize with required scope(s).

        Args:
            required_scopes: Single scope string or list of scopes.
                If list, ALL scopes in the list must be present (AND logic).
        """
        self.required_scopes = (
            required_scopes if isinstance(required_scopes, list) else [required_scopes]
        )

    @staticmethod
    def _satisfies(required: str, granted: set[str]) -> bool:
        """True when a granted set satisfies one required scope.

        Exact match, or the coarse product grant that implies it. The
        implication is deliberately one-directional and shape-restricted:
        only a three-segment ``products:`` scope has a coarse form, so no
        other scope namespace gains an implication by accident.
        """
        if required in granted:
            return True
        namespace, _, remainder = required.partition(":")
        if namespace != _PRODUCT_SCOPE_NAMESPACE:
            return False
        product_type, sep, action = remainder.partition(":")
        if not sep or not product_type or ":" in action:
            return False
        return f"{_PRODUCT_SCOPE_NAMESPACE}:{action}" in granted

    def enforce(self, granted_scopes: list[str]) -> bool:
        """Check if granted scopes satisfy the requirement.

        Returns True if every required scope is granted, directly or by the
        coarse-implies-per-product relation in :meth:`_satisfies`.
        """
        granted_set = set(granted_scopes)
        return all(self._satisfies(scope, granted_set) for scope in self.required_scopes)

    def enforce_or_raise(self, granted_scopes: list[str]) -> None:
        """Raise ValueError if granted scopes do not satisfy the requirement."""
        if not self.enforce(granted_scopes):
            missing = set(self.required_scopes) - set(granted_scopes)
            raise ValueError(f"Missing required scopes: {missing}")
