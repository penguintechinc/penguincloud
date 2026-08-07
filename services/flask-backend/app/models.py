"""Database runtime models (async-first with penguin-dal AsyncDB).

Schema definitions moved to models_sqlalchemy.py for Alembic.
All DB operations here are async and use penguin-dal.
"""

from __future__ import annotations

from typing import Any

from penguin_dal.quart_ext import get_db

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
) -> int | None:
    """Create a new user (async)."""
    db = get_db()
    user_id = await db.users.insert(
        email=email,
        password_hash=password_hash,
        full_name=full_name,
        role=role,
    )
    return user_id


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
    """Check if refresh token is valid (async)."""
    db = get_db()
    rows = await db(
        (db.refresh_tokens.user_id == user_id) &
        (db.refresh_tokens.token_hash == token_hash) &
        (db.refresh_tokens.revoked is False)  # type: ignore[operator]
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
