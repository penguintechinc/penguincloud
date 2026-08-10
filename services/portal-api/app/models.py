"""Database runtime models (async-first with penguin-dal AsyncDB).

Schema definitions moved to models_sqlalchemy.py for Alembic.
All DB operations here are async and use penguin-dal.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from penguin_dal.quart_ext import get_db

#: Operand for SQL boolean predicates built through penguin-dal's FieldProxy.
#: Bound to a name so the expression reads as a SQL predicate and does not trip
#: flake8's E712, which targets Python identity comparisons rather than these.
SQL_FALSE: Any = False

#: Placeholder substituted for stored credentials on every read that can reach
#: a response body. Matches the pre-migration masking value byte-for-byte.
MASKED_SECRET = "***"

#: Credential columns on product_connections. Stored encrypted at rest; even
#: the ciphertext never leaves the service, so both are masked on egress.
SECRET_FIELDS = ("api_key", "api_secret")

#: Fallback quotas for tenant rows written before max_users/max_products
#: gained a server default. Both columns were nullable with a Python-side
#: SQLAlchemy default only, which penguin-dal's own INSERTs never apply.
DEFAULT_MAX_USERS = 10
DEFAULT_MAX_PRODUCTS = 5


__all__ = [
    "get_db",
    "create_user",
    "get_user_by_email",
    "get_user_by_id",
    "get_user_teams",
    "update_user",
    "delete_user",
    "list_users",
    "create_mfa_secret",
    "enable_mfa",
    "disable_mfa",
    "get_tenant_by_slug",
    "get_tenant_by_id",
    "get_user_tenants",
    "get_user_tenant_role",
    "get_tenant_members",
    "add_tenant_member",
    "get_tenant_member_count",
    "create_tenant",
    "get_tenant_product_count",
    "create_product_connection",
    "get_product_connection_by_id",
    "get_product_connection_raw",
    "get_tenant_product_connections",
    "get_tenant_product_types",
    "update_product_health",
    "create_audit_log",
    "get_oauth_connection",
    "get_oauth_connection_by_provider_id",
    "store_oauth_connection",
    "is_refresh_token_valid",
    "store_refresh_token",
    "get_refresh_token_by_hash",
    "revoke_refresh_token",
    "revoke_all_user_tokens",
    "get_product_tenant_map",
    "set_product_tenant_map",
    "delete_product_tenant_map",
    "VALID_ROLES",
    "VALID_PLANS",
    "VALID_TENANT_KINDS",
    "VALID_TENANT_ROLES",
    "VALID_EXTERNAL_KINDS",
    "VALID_AUTH_TYPES",
    "VALID_HEALTH_STATUSES",
    "PRODUCT_TYPES",
    "PRODUCT_CATEGORIES",
    "MASKED_SECRET",
    "SECRET_FIELDS",
    "DEFAULT_MAX_USERS",
    "DEFAULT_MAX_PRODUCTS",
    "tenant_quota",
]

# Constants (from old models.py)
VALID_ROLES = ["admin", "maintainer", "viewer"]
VALID_PLANS = ["free", "starter", "business", "enterprise"]
VALID_TENANT_ROLES = ["owner", "admin", "member", "viewer"]
VALID_AUTH_TYPES = ["bearer", "basic", "api_key", "none"]
VALID_HEALTH_STATUSES = ["healthy", "degraded", "unhealthy", "unknown"]
PRODUCT_TYPES = [
    "marchproxy",
    "squawk",
    "license_server",
    "skauswatch",
    "waddleai",
    "articdbm",
    "cerberus",
    "waddlebot",
    "waddleperf",
    "iceshelves",
    "icecharts",
    "killkrill",
    "tobogganing",
    "nest",
    "darwin",
    "gough",
    "current",
    "elder",
    "admin",
    "generic",
]
PRODUCT_CATEGORIES = {
    "infrastructure": ["marchproxy", "squawk", "articdbm", "iceshelves"],
    "security": ["skauswatch", "cerberus"],
    "ai": ["waddleai", "waddlebot"],
    "monitoring": ["waddleperf", "icecharts"],
    "operations": [
        "killkrill",
        "tobogganing",
        "darwin",
        "gough",
        "current",
        "license_server",
    ],
    "development": ["nest"],
    "legacy": ["elder"],
    "administration": ["admin"],
}


def tenant_quota(tenant: dict[str, Any], field: str, fallback: int) -> int:
    """Read an integer quota off a tenant row, tolerating a legacy NULL.

    dict.get(key, default) returns None for a key that is present and
    NULL, so quota comparisons must coalesce explicitly or they raise
    TypeError ("'>=' not supported between 'int' and 'NoneType'").
    """
    value = tenant.get(field)
    return int(value) if value is not None else fallback


async def create_user(
    email: str,
    password_hash: str,
    full_name: str = "",
    role: str = "viewer",
) -> dict[str, Any] | None:
    """Create a new user (async).

    Enforces the development-mode single-user cap before inserting. The
    routes check it first and answer a clean 403; this is the backstop, so
    a call site that forgets — a future route, a seed script, a background
    job — cannot silently breach the cap. Raises
    :class:`~app.devmode.DevModeUserCapExceeded`.
    """
    from . import devmode

    await devmode.assert_user_creation_allowed()

    db = get_db()
    now = datetime.now(UTC)
    user_id = await db.users.async_insert(
        email=email,
        password_hash=password_hash,
        full_name=full_name,
        role=role,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    if user_id:
        row = await db(db.users.id == user_id).select()
        return dict(row[0]) if row else None
    return None


async def get_user_by_email(email: str) -> dict[str, Any] | None:
    """Get user by email (async)."""
    db = get_db()
    row = await db(db.users.email == email).select()
    return dict(row[0]) if row else None


async def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    """Get user by ID (async)."""
    db = get_db()
    row = await db(db.users.id == user_id).select()
    return dict(row[0]) if row else None


async def store_refresh_token(
    user_id: int, token_hash: str, expires_at: Any
) -> int | None:
    """Store refresh token (async)."""
    db = get_db()
    new_id: int | None = await db.refresh_tokens.async_insert(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        revoked=False,
        created_at=datetime.now(UTC),
    )
    return new_id


async def get_refresh_token_by_hash(token_hash: str) -> dict[str, Any] | None:
    """Look up a stored refresh token by its hash, ignoring validity (async).

    Identifies which user presented the token so the caller can then
    authorise it with is_refresh_token_valid(). Deliberately unfiltered:
    a revoked or expired row must still be findable, otherwise a replayed
    token is indistinguishable from an unknown one for auditing.
    """
    db = get_db()
    rows = await db(db.refresh_tokens.token_hash == token_hash).select()
    return dict(rows[0]) if rows else None


async def is_refresh_token_valid(user_id: int, token_hash: str) -> bool:
    """Check if refresh token is valid and not expired (async)."""
    db = get_db()
    rows = await db(
        (db.refresh_tokens.user_id == user_id)
        & (db.refresh_tokens.token_hash == token_hash)
        & (db.refresh_tokens.revoked == SQL_FALSE)
        & (db.refresh_tokens.expires_at > datetime.now(UTC))
    ).select()
    return len(rows) > 0


async def revoke_refresh_token(token_hash: str) -> None:
    """Revoke a refresh token (async)."""
    db = get_db()
    await db(db.refresh_tokens.token_hash == token_hash).update(revoked=True)


async def revoke_all_user_tokens(user_id: int) -> int:
    """Revoke all refresh tokens for a user; return how many were revoked."""
    db = get_db()
    revoked = await db(db.refresh_tokens.user_id == user_id).update(revoked=True)
    return int(revoked or 0)


async def get_mfa_secret(user_id: int) -> dict[str, Any] | None:
    """Get MFA secret (async)."""
    db = get_db()
    row = await db(db.mfa_secrets.user_id == user_id).select()
    return dict(row[0]) if row else None


async def is_mfa_enabled(user_id: int) -> bool:
    """Check if MFA is enabled (async)."""
    db = get_db()
    row = await db(db.mfa_secrets.user_id == user_id).select()
    return bool(row and row[0].enabled_at)


#: Tenant kinds. Stored as a plain string column (see models_sqlalchemy) so
#: the ORM, the Alembic migration and penguin-dal's runtime INSERTs all agree
#: on the same lowercase values.
VALID_TENANT_KINDS = ["provider", "customer"]

#: External identifier kinds a product connection can be mapped by.
VALID_EXTERNAL_KINDS = ["tenant_id", "organization_id", "namespace"]


async def create_tenant(
    name: str,
    slug: str,
    owner_id: int,
    plan_tier: str = "free",
    display_name: str = "",
    parent_tenant_id: int | None = None,
    kind: str = "customer",
    depth: int = 0,
) -> int | None:
    """Create a new tenant and enrol the owner as a member (async).

    The owner row in tenant_members is what get_user_tenant_role() reads, so
    without it the creator cannot switch to, or act on, the tenant they just
    created.

    ``parent_tenant_id``/``depth`` are written here rather than defaulted by
    the schema: penguin-dal issues its own INSERTs and never applies
    SQLAlchemy's Python-side defaults, and the brief puts depth maintenance
    in the service layer rather than in a trigger. Callers must validate the
    parent (existence, authority, cycles) before calling — see
    ``app.tenancy.hierarchy.validate_parent``.
    """
    db = get_db()
    new_id: int | None = await db.tenants.async_insert(
        name=name,
        slug=slug,
        display_name=display_name or name,
        owner_id=owner_id,
        plan_tier=plan_tier,
        parent_tenant_id=parent_tenant_id,
        kind=kind,
        depth=depth,
    )
    if new_id is None:
        return None

    await db.tenant_members.async_insert(
        tenant_id=new_id,
        user_id=owner_id,
        role="owner",
    )
    return new_id


async def get_tenant_by_id(tenant_id: int) -> dict[str, Any] | None:
    """Get tenant by ID (async)."""
    db = get_db()
    row = await db(db.tenants.id == tenant_id).select()
    return dict(row[0]) if row else None


async def create_team(name: str, slug: str, owner_id: int) -> dict[str, Any] | None:
    """Create a new team (async)."""
    db = get_db()
    team_id = await db.teams.async_insert(name=name, slug=slug, owner_id=owner_id)
    if team_id:
        row = await db(db.teams.id == team_id).select()
        return dict(row[0]) if row else None
    return None


async def get_team_by_id(team_id: int) -> dict[str, Any] | None:
    """Get team by ID (async)."""
    db = get_db()
    row = await db(db.teams.id == team_id).select()
    return dict(row[0]) if row else None


async def get_team_members(team_id: int) -> list[dict[str, Any]]:
    """Get team members (async)."""
    db = get_db()
    rows = await db(db.team_members.team_id == team_id).select()
    return [dict(row) for row in rows]


async def add_team_member(
    team_id: int, user_id: int, role: str = "member"
) -> int | None:
    """Add user to team (async)."""
    db = get_db()
    new_id: int | None = await db.team_members.async_insert(
        team_id=team_id, user_id=user_id, role=role
    )
    return new_id


async def get_user_teams(user_id: int) -> list[dict[str, Any]]:
    """Get all teams for a user (async)."""
    db = get_db()
    rows = await db(db.team_members.user_id == user_id).select()
    return [dict(row) for row in rows]


async def get_user_team_role(user_id: int, team_id: int) -> str | None:
    """Get user's role in a team (async)."""
    db = get_db()
    row = await db(
        (db.team_members.user_id == user_id) & (db.team_members.team_id == team_id)
    ).select()
    return row[0].role if row else None


async def create_oauth_connection(
    user_id: int,
    provider: str,
    provider_user_id: str,
    access_token: str,
    refresh_token: str | None = None,
) -> int | None:
    """Create OAuth connection (async)."""
    db = get_db()
    new_id: int | None = await db.oauth_connections.async_insert(
        user_id=user_id,
        provider=provider,
        provider_user_id=provider_user_id,
        access_token=access_token,
        refresh_token=refresh_token,
    )
    return new_id


async def update_user(user_id: int, **kwargs: Any) -> dict[str, Any] | None:
    """Update user by ID (async)."""
    db = get_db()
    allowed_fields = {"email", "password_hash", "full_name", "role", "is_active"}
    update_data = {k: v for k, v in kwargs.items() if k in allowed_fields}
    if not update_data:
        return await get_user_by_id(user_id)
    await db(db.users.id == user_id).update(**update_data)
    return await get_user_by_id(user_id)


async def delete_user(user_id: int) -> bool:
    """Delete user by ID (async)."""
    db = get_db()
    rows = await db(db.users.id == user_id).delete()
    return bool(rows)


async def list_users(
    page: int = 1, per_page: int = 20
) -> tuple[list[dict[str, Any]], int]:
    """List users with pagination (async)."""
    # NOTE: Client-side pagination; penguin-dal server-side support deferred
    db = get_db()
    # Get all users (improved pagination in Phase 1b)
    users_query: Any = db.users
    rows: list[Any] = []
    try:
        rows = await users_query.select()
    except Exception:
        # Empty table or query error
        return [], 0
    offset = (page - 1) * per_page
    limit = offset + per_page
    paginated = [dict(u) for u in rows[offset:limit]]
    return paginated, len(rows)


async def create_mfa_secret(
    user_id: int, secret: str, backup_codes: str
) -> dict[str, Any] | None:
    """Store MFA secret for user (async)."""
    db = get_db()
    await db.mfa_secrets.async_insert(
        user_id=user_id,
        secret=secret,
        backup_codes=backup_codes,
    )
    return await get_mfa_secret(user_id)


async def enable_mfa(user_id: int) -> bool:
    """Enable MFA for user (async)."""
    db = get_db()
    rows = await db(db.mfa_secrets.user_id == user_id).update(
        # now(UTC), not utcnow(): utcnow() is deprecated on 3.12+ and
        # returns a NAIVE datetime, which compares as local time against
        # the timezone-aware values written everywhere else in this module.
        enabled_at=datetime.now(UTC)
    )
    return bool(rows)


async def disable_mfa(user_id: int) -> bool:
    """Disable MFA for user (async)."""
    db = get_db()
    rows = await db(db.mfa_secrets.user_id == user_id).delete()
    return bool(rows)


async def get_tenant_by_slug(slug: str) -> dict[str, Any] | None:
    """Get tenant by slug (async)."""
    db = get_db()
    row = await db(db.tenants.slug == slug).select()
    return dict(row[0]) if row else None


async def get_user_tenants(user_id: int) -> list[dict[str, Any]]:
    """Get all tenants a user is a member of (async)."""
    db = get_db()
    memberships = await db(db.tenant_members.user_id == user_id).select()
    if not memberships:
        return []
    tenant_ids = [m.tenant_id for m in memberships]
    tenants = await db(db.tenants.id.belongs(tenant_ids)).select()
    result = []
    for t in tenants:
        td = dict(t)
        membership = next((m for m in memberships if m.tenant_id == t.id), None)
        td["user_role"] = membership.role if membership else None
        result.append(td)
    return result


async def get_user_tenant_role(user_id: int, tenant_id: int) -> str | None:
    """Get user's role in a tenant (async)."""
    db = get_db()
    row = await db(
        (db.tenant_members.user_id == user_id)
        & (db.tenant_members.tenant_id == tenant_id)
    ).select()
    return row[0].role if row else None


async def get_tenant_members(tenant_id: int) -> list[dict[str, Any]]:
    """Get all members of a tenant with user details (async)."""
    db = get_db()
    members = await db(db.tenant_members.tenant_id == tenant_id).select()
    result = []
    for m in members:
        md = dict(m)
        user_row = await db(db.users.id == m.user_id).select()
        if user_row:
            md["user_email"] = user_row[0].email
            md["user_full_name"] = user_row[0].full_name
        result.append(md)
    return result


async def add_tenant_member(
    tenant_id: int, user_id: int, role: str = "member", invited_by_id: int | None = None
) -> dict[str, Any] | None:
    """Add a member to a tenant (async)."""
    db = get_db()
    member_id = await db.tenant_members.async_insert(
        tenant_id=tenant_id,
        user_id=user_id,
        role=role,
        invited_by_id=invited_by_id,
    )
    if member_id:
        row = await db(db.tenant_members.id == member_id).select()
        return dict(row[0]) if row else None
    return None


async def get_tenant_member_count(tenant_id: int) -> int:
    """Get the count of members in a tenant (async)."""
    db = get_db()
    rows = await db(db.tenant_members.tenant_id == tenant_id).select()
    return len(rows)


async def create_product_connection(
    tenant_id: int,
    product_type: str,
    display_name: str,
    base_url: str,
    auth_type: str = "bearer",
    api_key: str = "",
    api_secret: str = "",
    health_endpoint: str = "/healthz",
    api_version: str = "v1",
    discovered: bool = False,
) -> int | None:
    """Create a new product connection (async)."""
    from .encryption import encrypt_value

    db = get_db()
    new_id: int | None = await db.product_connections.async_insert(
        tenant_id=tenant_id,
        product_type=product_type,
        display_name=display_name,
        base_url=base_url.rstrip("/"),
        api_key=encrypt_value(api_key) if api_key else "",
        api_secret=encrypt_value(api_secret) if api_secret else "",
        auth_type=auth_type,
        health_endpoint=health_endpoint,
        api_version=api_version,
        discovered=discovered,
    )
    return new_id


async def get_product_connection_by_id(conn_id: int) -> dict[str, Any] | None:
    """Get product connection by ID with credentials masked (async).

    Every caller of this function feeds a response body, so api_key and
    api_secret are replaced with MASKED_SECRET here rather than at each
    call site. get_product_connection_raw is the one sanctioned path to
    the stored ciphertext.
    """
    db = get_db()
    row = await db(db.product_connections.id == conn_id).select()
    return _mask_connection_secrets(dict(row[0])) if row else None


def _mask_connection_secrets(conn: dict[str, Any]) -> dict[str, Any]:
    """Replace stored credential values with MASKED_SECRET.

    Empty/absent credentials stay an empty string so clients can tell
    "no credential configured" from "credential set but withheld".
    """
    for field in SECRET_FIELDS:
        conn[field] = MASKED_SECRET if conn.get(field) else ""
    return conn


async def get_product_connection_raw(conn_id: int) -> dict[str, Any] | None:
    """Get product connection including stored credential ciphertext (async).

    INTERNAL USE ONLY — the returned dict must never reach a response
    body. Callers are the proxy and adapter paths, which decrypt the
    credentials to authenticate outbound calls to the connected product.
    """
    db = get_db()
    row = await db(db.product_connections.id == conn_id).select()
    if row:
        conn = dict(row[0])
        # api_key and api_secret remain encrypted at this layer
        return conn
    return None


async def get_tenant_product_connections(tenant_id: int) -> list[dict[str, Any]]:
    """Get all product connections for a tenant, credentials masked (async)."""
    db = get_db()
    rows = await db(db.product_connections.tenant_id == tenant_id).select()
    return [_mask_connection_secrets(dict(row)) for row in rows]


async def get_tenant_product_types(tenant_id: int) -> set[str]:
    """Get the distinct product types a tenant has connections to (async).

    Selects the one column it needs rather than reusing
    ``get_tenant_product_connections``: this runs inside ``resolve_scopes``,
    so it is on the authorization path for every proxied request, and the
    fuller accessor builds a dict and masks credentials for every row to
    answer a question about column values.

    Rows with an empty product_type are dropped — a scope derived from one
    would be ``products::read``, which no rule can require and which reads
    like a malformed grant in an audit trail.
    """
    db = get_db()
    rows = await db(db.product_connections.tenant_id == tenant_id).select(
        db.product_connections.product_type
    )
    return {str(row["product_type"]) for row in rows if row["product_type"]}


async def get_tenant_product_count(tenant_id: int) -> int:
    """Get the count of product connections for a tenant (async)."""
    db = get_db()
    rows = await db(db.product_connections.tenant_id == tenant_id).select()
    return len(rows)


async def update_product_health(
    conn_id: int, status: str, last_check: Any = None
) -> bool:
    """Update product connection health status and timestamp (async).

    The column is `last_health_check` (models_sqlalchemy.ProductConnection);
    writing `health_check_at` raises "Unconsumed column names", so every
    health check failed to record. Defaults the timestamp to now rather
    than writing NULL — a recorded status with no time is not useful.
    """
    db = get_db()
    rows = await db(db.product_connections.id == conn_id).update(
        health_status=status,
        last_health_check=last_check or datetime.now(UTC),
    )
    return bool(rows)


async def create_audit_log(
    user_id: int | None,
    tenant_id: int,
    action: str,
    resource_type: str,
    resource_id: str,
    changes: str | None = None,
    ip_address: str | None = None,
) -> int | None:
    """Create audit log entry (async).

    Column names follow the audit_logs schema in models_sqlalchemy.py:
    the action lands in `action_type`, and the change summary in the
    Text column exposed to the DB as `metadata` — inserting `action`
    or `changes` raises "Unconsumed column names".
    """
    db = get_db()
    new_id: int | None = await db.audit_logs.async_insert(
        user_id=user_id,
        tenant_id=tenant_id,
        action_type=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=changes,
        ip_address=ip_address,
    )
    return new_id


async def get_oauth_connection(user_id: int, provider: str) -> dict[str, Any] | None:
    """Get OAuth connection for user and provider (async)."""
    db = get_db()
    row = await db(
        (db.oauth_connections.user_id == user_id)
        & (db.oauth_connections.provider == provider)
    ).select()
    return dict(row[0]) if row else None


async def get_oauth_connection_by_provider_id(
    provider: str, provider_user_id: str
) -> dict[str, Any] | None:
    """Get OAuth connection by provider and provider user ID (async)."""
    db = get_db()
    row = await db(
        (db.oauth_connections.provider == provider)
        & (db.oauth_connections.provider_user_id == provider_user_id)
    ).select()
    return dict(row[0]) if row else None


async def store_oauth_connection(
    user_id: int,
    provider: str,
    provider_user_id: str,
    access_token: str,
    refresh_token: str | None = None,
    expires_at: Any = None,
) -> int | None:
    """Store or update OAuth connection (async)."""
    db = get_db()
    existing = await get_oauth_connection(user_id, provider)
    if existing:
        # Update existing connection
        await db(
            (db.oauth_connections.user_id == user_id)
            & (db.oauth_connections.provider == provider)
        ).update(
            provider_user_id=provider_user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )
        return existing.get("id")
    else:
        # Create new connection
        new_id: int | None = await db.oauth_connections.async_insert(
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )
        return new_id


async def get_product_tenant_map(
    connection_id: int, tenant_id: int
) -> dict[str, Any] | None:
    """Get product tenant mapping by connection and tenant (async)."""
    db = get_db()
    row = await db(
        (db.product_tenant_map.connection_id == connection_id)
        & (db.product_tenant_map.tenant_id == tenant_id)
    ).select()
    return dict(row[0]) if row else None


async def set_product_tenant_map(
    connection_id: int, tenant_id: int, external_kind: str, external_id: str
) -> int | None:
    """Set or update product tenant mapping (async).

    Returns the mapping ID (inserted or existing).
    """
    db = get_db()
    existing = await get_product_tenant_map(connection_id, tenant_id)
    if existing:
        # Update existing mapping
        await db(
            (db.product_tenant_map.connection_id == connection_id)
            & (db.product_tenant_map.tenant_id == tenant_id)
        ).update(
            external_kind=external_kind,
            external_id=external_id,
            updated_at=datetime.now(UTC),
        )
        return existing.get("id")
    else:
        # Create new mapping
        new_id: int | None = await db.product_tenant_map.async_insert(
            connection_id=connection_id,
            tenant_id=tenant_id,
            external_kind=external_kind,
            external_id=external_id,
        )
        return new_id


async def delete_product_tenant_map(connection_id: int, tenant_id: int) -> bool:
    """Delete product tenant mapping (async)."""
    db = get_db()
    rows = await db(
        (db.product_tenant_map.connection_id == connection_id)
        & (db.product_tenant_map.tenant_id == tenant_id)
    ).delete()
    return bool(rows)
