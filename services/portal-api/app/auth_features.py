"""Password reset, email confirmation, sessions, API keys, audit logging."""

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from quart import current_app, request

from .models import get_db

#: Operands for SQL NULL / boolean predicates built through penguin-dal's
#: FieldProxy, which exposes no isnull() helper — its comparison operators are
#: the public API. Bound to names rather than written as `== None` / `== True`
#: literals: flake8's E711/E712 target Python identity comparisons, which these
#: are not, and a name keeps the intent (a SQL predicate) explicit.
SQL_NULL: Any = None
SQL_TRUE: Any = True
SQL_FALSE: Any = False


# Password reset
async def create_password_reset_token(user_id: int) -> tuple[str, datetime]:
    """Create password reset token (async)."""
    token = secrets.token_hex(16)
    expires = datetime.now(UTC) + timedelta(hours=1)
    db = get_db()
    # async_insert, not insert: insert() is the sync API and opens a session
    # via `with`, so awaiting it raises "'AsyncSession' object does not
    # support the context manager protocol".
    await db.password_reset_tokens.async_insert(
        user_id=user_id,
        token=token,
        expires_at=expires,
    )
    return token, expires


async def validate_password_reset_token(token: str) -> int | None:
    """Validate reset token, return user_id or None (async)."""
    db = get_db()
    rows = await db(
        (db.password_reset_tokens.token == token)
        & (db.password_reset_tokens.expires_at > datetime.now(UTC))
        & (db.password_reset_tokens.used_at == SQL_NULL)
    ).select()
    return rows[0]["user_id"] if rows else None


async def mark_token_used(token: str) -> None:
    """Mark password reset token as used (async)."""
    db = get_db()
    await db(db.password_reset_tokens.token == token).update(used_at=datetime.now(UTC))


# Email confirmation
async def create_email_confirmation_token(user_id: int) -> tuple[str, datetime]:
    """Create email confirmation token (async)."""
    token = secrets.token_hex(16)
    expires = datetime.now(UTC) + timedelta(hours=24)
    db = get_db()
    await db.email_confirmation_tokens.async_insert(
        user_id=user_id,
        token=token,
        expires_at=expires,
    )
    return token, expires


async def validate_email_token(token: str) -> int | None:
    """Validate email token, return user_id or None (async)."""
    db = get_db()
    rows = await db(
        (db.email_confirmation_tokens.token == token)
        & (db.email_confirmation_tokens.expires_at > datetime.now(UTC))
        & (db.email_confirmation_tokens.confirmed_at == SQL_NULL)
    ).select()
    return rows[0]["user_id"] if rows else None


async def confirm_email(token: str) -> bool:
    """Mark email as confirmed (async)."""
    db = get_db()
    await db(db.email_confirmation_tokens.token == token).update(confirmed_at=datetime.now(UTC))
    return True


# API keys
async def create_api_key(user_id: int, name: str, scopes: str = "") -> tuple[str, str]:
    """Create API key. Returns (full_key, key_id) (async)."""
    prefix = "pk_live" if not current_app.config.get("DEBUG") else "pk_test"
    key = f"{prefix}_{secrets.token_hex(16)}"
    key_hash = hashlib.sha256(key.encode()).hexdigest()

    db = get_db()
    # key_prefix is the schema's column name (models_sqlalchemy.APIKey);
    # inserting `prefix` raises "Unconsumed column names", and it is what
    # get_user_api_keys reads back.
    key_id = await db.api_keys.async_insert(
        user_id=user_id,
        name=name,
        key_hash=key_hash,
        key_prefix=prefix,
        scopes=scopes or "",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    return key, str(key_id)


async def validate_api_key(key: str) -> dict[str, Any] | None:
    """Validate API key, return key record or None (async)."""
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    db = get_db()
    rows = await db(
        (db.api_keys.key_hash == key_hash) & (db.api_keys.is_active == SQL_TRUE)
    ).select()
    if rows:
        record = rows[0]
        await db(db.api_keys.id == record["id"]).update(last_used_at=datetime.now(UTC))
        return dict(record)
    return None


async def revoke_api_key(key_id: int, user_id: int) -> bool:
    """Revoke an API key (async)."""
    db = get_db()
    updated = await db((db.api_keys.id == key_id) & (db.api_keys.user_id == user_id)).update(
        is_active=False
    )
    return updated > 0


async def get_user_api_keys(user_id: int) -> list[dict[str, Any]]:
    """List API keys for user (without full key) (async)."""
    db = get_db()
    keys = await db(db.api_keys.user_id == user_id).select(orderby=~db.api_keys.created_at)
    return [
        {
            "id": k["id"],
            "name": k["name"],
            "prefix": k["key_prefix"],
            "last_used_at": (k["last_used_at"].isoformat() if k.get("last_used_at") else None),
            "expires_at": k["expires_at"].isoformat() if k.get("expires_at") else None,
            "created_at": k["created_at"].isoformat() if k.get("created_at") else None,
        }
        for k in keys
    ]


# Audit logging
async def audit_log(
    action: str,
    tenant_id: int,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    user_id: int | None = None,
) -> None:
    """Log an audit event (async).

    Writes `action_type` (the schema's column name, not `action`) via
    async_insert so the coroutine is actually awaited.

    ``tenant_id`` is required. It was absent, so every row this writer
    produced carried a NULL tenant — unreachable by any tenant-scoped
    reader, and therefore an audit record that exists but can never be
    read. It has no callers today; requiring the tenant means a future one
    cannot reintroduce untenanted rows for the readers above to miss.
    ``models.create_audit_log`` is the writer the app actually uses and has
    always required it.
    """
    db = get_db()
    remote_addr = request.remote_addr if request else None
    user_agent = request.headers.get("User-Agent") if request else None
    await db.audit_logs.async_insert(
        user_id=user_id,
        tenant_id=tenant_id,
        action_type=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=remote_addr,
        user_agent=user_agent,
        metadata=json.dumps(metadata) if metadata else None,
    )


async def get_audit_logs(tenant_id: int, limit: int = 100) -> list[dict[str, Any]]:
    """Get recent audit logs for ONE tenant (async).

    ``tenant_id`` is the first parameter and has no default, deliberately.
    This function used to read ``db(db.audit_logs.id > 0)`` — every row in
    the deployment — and was served by ``GET /api/v1/users/audit-logs``
    behind a scope check with no tenant predicate at all. Any caller
    holding ``audit:read`` in any tenant read every other tenant's audit
    trail: who did what, to which resource, under which user id. In a
    portal whose entire premise is provider/customer isolation that is the
    worst-shaped disclosure available, because audit rows describe other
    customers' activity by name.

    Making the parameter required rather than optional is the point: a
    caller that forgets it gets a TypeError at the call site, not a
    silently deployment-wide result set.
    """
    db = get_db()
    logs = await db(db.audit_logs.tenant_id == tenant_id).select(
        orderby=~db.audit_logs.created_at,
        limitby=(0, limit),
    )
    return [
        {
            "id": log["id"],
            "user_id": log["user_id"],
            "action": log["action_type"],
            "resource_type": log["resource_type"],
            "resource_id": log["resource_id"],
            "ip_address": log["ip_address"],
            "created_at": (log["created_at"].isoformat() if log.get("created_at") else None),
        }
        for log in logs
    ]


# Session management
async def get_user_sessions(user_id: int) -> list[dict[str, Any]]:
    """List active sessions (refresh tokens) for user (async)."""
    db = get_db()
    # `~field` is penguin-dal's descending-ORDER-BY sugar (see the orderby
    # below), not a boolean NOT — using it as a predicate raises
    # "Neither 'UnaryExpression' object nor 'Comparator' object has an
    # attribute '_clause'". Compare the column instead.
    tokens = await db(
        (db.refresh_tokens.user_id == user_id)
        & (db.refresh_tokens.revoked == SQL_FALSE)
        & (db.refresh_tokens.expires_at > datetime.now(UTC))
    ).select(orderby=~db.refresh_tokens.created_at)
    return [
        {
            "id": t["id"],
            "device_info": t.get("device_info") or "",
            "ip_address": t.get("ip_address") or "",
            "created_at": t["created_at"].isoformat() if t.get("created_at") else None,
            "expires_at": t["expires_at"].isoformat() if t.get("expires_at") else None,
        }
        for t in tokens
    ]


async def revoke_session(session_id: int, user_id: int) -> bool:
    """Revoke a user session (async)."""
    db = get_db()
    updated = await db(
        (db.refresh_tokens.id == session_id) & (db.refresh_tokens.user_id == user_id)
    ).update(revoked=True)
    return updated > 0
