"""Tenancy management module."""

from .authz import (
    ADMIN_ROLES,
    DELEGATED_ADMIN,
    EFFECTIVE_ADMIN_ROLES,
    UNSCOPED_SCOPES,
    has_delegated_admin,
    may_bind_tenant,
    may_switch_to_tenant,
    resolve_effective_role,
    resolve_scopes,
)
from .hierarchy import (
    ParentValidation,
    recompute_subtree_depth,
    set_parent,
    validate_origin_authority,
    validate_parent,
)
from .middleware import TenancyContext, get_tenancy_context, tenancy_aware
from .resolver import (
    MAX_HIERARCHY_DEPTH,
    TenantHierarchy,
    clear_local_cache,
    get_ancestors,
    get_descendants,
    get_hierarchy,
    invalidate_ancestors,
    invalidate_subtree,
    invalidate_tenant,
)

__all__ = [
    "ADMIN_ROLES",
    "DELEGATED_ADMIN",
    "EFFECTIVE_ADMIN_ROLES",
    "MAX_HIERARCHY_DEPTH",
    "UNSCOPED_SCOPES",
    "ParentValidation",
    "TenancyContext",
    "TenantHierarchy",
    "clear_local_cache",
    "get_ancestors",
    "get_descendants",
    "get_hierarchy",
    "get_tenancy_context",
    "has_delegated_admin",
    "invalidate_ancestors",
    "invalidate_subtree",
    "invalidate_tenant",
    "may_bind_tenant",
    "may_switch_to_tenant",
    "recompute_subtree_depth",
    "resolve_effective_role",
    "resolve_scopes",
    "set_parent",
    "tenancy_aware",
    "validate_origin_authority",
    "validate_parent",
]
