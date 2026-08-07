"""Database runtime models (async-first with penguin-dal AsyncDB).

Schema definitions moved to models_sqlalchemy.py for Alembic.
All DB operations here are async and use penguin-dal.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from penguin_dal.quart_ext import get_db

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
    "update_product_health",
    "create_audit_log",
    "get_oauth_connection",
    "get_oauth_connection_by_provider_id",
    "store_oauth_connection",
    "is_refresh_token_valid",
    "store_refresh_token",
    "VALID_ROLES",
    "VALID_PLANS",
    "VALID_TENANT_ROLES",
    "VALID_AUTH_TYPES",
    "VALID_HEALTH_STATUSES",
    "PRODUCT_TYPES",
    "PRODUCT_CATEGORIES",
]

# Constants (from old models.py)
VALID_ROLES = ["admin", "maintainer", "viewer"]
VALID_PLANS = ["free", "starter", "business", "enterprise"]
VALID_TENANT_ROLES = ["owner", "admin", "member", "viewer"]
VALID_AUTH_TYPES = ["bearer", "basic", "api_key", "none"]
VALID_HEALTH_STATUSES = ["healthy", "degraded", "unhealthy", "unknown"]
PRODUCT_TYPES = [
    "marchproxy", "squawk", "license_server", "skauswatch", "waddleai",
    "articdbm", "cerberus", "waddlebot", "waddleperf", "iceshelves",
    "icecharts", "killkrill", "tobogganing", "nest", "darwin", "gough",
    "current", "elder", "admin", "generic",
]
PRODUCT_CATEGORIES = {
    "infrastructure": [
        "marchproxy", "squawk", "articdbm", "iceshelves"
    ],
    "security": ["skauswatch", "cerberus"],
    "ai": ["waddleai", "waddlebot"],
    "monitoring": ["waddleperf", "icecharts"],
    "operations": [
        "killkrill", "tobogganing", "darwin", "gough", "current", "license_server"
    ],
    "development": ["nest"],
    "legacy": ["elder"],
    "administration": ["admin"],
}


async def create_user(
    email: str,
    password_hash: str,
    full_name: str = "",
    role: str = "viewer",
) -> dict[str, Any] | None:
    """Create a new user (async)."""
    db = get_db()
    user_id = await db.users.insert(
        email=email,
        password_hash=password_hash,
        full_name=full_name,
        role=role,
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
    return await db.refresh_tokens.insert(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
    )


async def is_refresh_token_valid(user_id: int, token_hash: str) -> bool:
    """Check if refresh token is valid and not expired (async)."""
    from datetime import datetime
    db = get_db()
    rows = await db(
        (db.refresh_tokens.user_id == user_id) &
        (db.refresh_tokens.token_hash == token_hash) &
        (db.refresh_tokens.revoked == False) &  # noqa: E712
        (db.refresh_tokens.expires_at > datetime.utcnow())
    ).select()
    return len(rows) > 0


async def revoke_refresh_token(token_hash: str) -> None:
    """Revoke a refresh token (async)."""
    db = get_db()
    await db(db.refresh_tokens.token_hash == token_hash).update(revoked=True)


async def revoke_all_user_tokens(user_id: int) -> None:
    """Revoke all refresh tokens for a user (async)."""
    db = get_db()
    await db(db.refresh_tokens.user_id == user_id).update(revoked=True)


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


async def create_tenant(
    name: str, slug: str, owner_id: int, plan_tier: str = "free"
) -> int | None:
    """Create a new tenant (async)."""
    db = get_db()
    return await db.tenants.insert(
        name=name,
        slug=slug,
        owner_id=owner_id,
        plan_tier=plan_tier,
    )


async def get_tenant_by_id(tenant_id: int) -> dict[str, Any] | None:
    """Get tenant by ID (async)."""
    db = get_db()
    row = await db(db.tenants.id == tenant_id).select()
    return dict(row[0]) if row else None


async def create_team(name: str, slug: str, owner_id: int) -> dict[str, Any] | None:
    """Create a new team (async)."""
    db = get_db()
    team_id = await db.teams.insert(name=name, slug=slug, owner_id=owner_id)
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
    return await db.team_members.insert(team_id=team_id, user_id=user_id, role=role)


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
    return await db.oauth_connections.insert(
        user_id=user_id,
        provider=provider,
        provider_user_id=provider_user_id,
        access_token=access_token,
        refresh_token=refresh_token,
    )


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
    await db.mfa_secrets.insert(
        user_id=user_id,
        secret=secret,
        backup_codes=backup_codes,
    )
    return await get_mfa_secret(user_id)


async def enable_mfa(user_id: int) -> bool:
    """Enable MFA for user (async)."""
    db = get_db()
    rows = await db(db.mfa_secrets.user_id == user_id).update(
        enabled_at=datetime.utcnow()
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


async def get_user_tenant_role(
    user_id: int, tenant_id: int
) -> str | None:
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
    member_id = await db.tenant_members.insert(
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
    return await db.product_connections.insert(
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


async def get_product_connection_by_id(conn_id: int) -> dict[str, Any] | None:
    """Get product connection by ID (async)."""
    db = get_db()
    row = await db(db.product_connections.id == conn_id).select()
    return dict(row[0]) if row else None


async def get_product_connection_raw(conn_id: int) -> dict[str, Any] | None:
    """Get product connection with encrypted fields (async)."""
    db = get_db()
    row = await db(db.product_connections.id == conn_id).select()
    if row:
        conn = dict(row[0])
        # api_key and api_secret remain encrypted at this layer
        return conn
    return None


async def get_tenant_product_connections(tenant_id: int) -> list[dict[str, Any]]:
    """Get all product connections for a tenant (async)."""
    db = get_db()
    rows = await db(db.product_connections.tenant_id == tenant_id).select()
    return [dict(row) for row in rows]


async def get_tenant_product_count(tenant_id: int) -> int:
    """Get the count of product connections for a tenant (async)."""
    db = get_db()
    rows = await db(db.product_connections.tenant_id == tenant_id).select()
    return len(rows)


async def update_product_health(
    conn_id: int, status: str, last_check: Any = None
) -> bool:
    """Update product connection health status (async)."""
    db = get_db()
    rows = await db(db.product_connections.id == conn_id).update(
        health_status=status,
        health_check_at=last_check,
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
    """Create audit log entry (async)."""
    db = get_db()
    return await db.audit_logs.insert(
        user_id=user_id,
        tenant_id=tenant_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        changes=changes,
        ip_address=ip_address,
    )


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
        return await db.oauth_connections.insert(
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )
