"""Password reset, email confirmation, sessions, API keys, audit logging."""

import hashlib
import secrets
from datetime import datetime, timedelta

import json

from flask import current_app, request

from .models import get_db


# Password reset
def create_password_reset_token(user_id: int) -> tuple[str, datetime]:
    """Create password reset token."""
    token = secrets.token_hex(16)
    expires = datetime.utcnow() + timedelta(hours=1)
    db = get_db()
    db.password_reset_tokens.insert(
        user_id=user_id,
        token=token,
        expires_at=expires,
    )
    db.commit()
    return token, expires


def validate_password_reset_token(token: str):
    """Validate reset token, return user_id or None."""
    db = get_db()
    record = (
        db(
            (db.password_reset_tokens.token == token)
            & (db.password_reset_tokens.expires_at > datetime.utcnow())
            & (db.password_reset_tokens.used_at is None)
        )
        .select()
        .first()
    )
    return record["user_id"] if record else None


def mark_token_used(token: str):
    """Mark password reset token as used."""
    db = get_db()
    db(db.password_reset_tokens.token == token).update(used_at=datetime.utcnow())
    db.commit()


# Email confirmation
def create_email_confirmation_token(user_id: int) -> tuple[str, datetime]:
    """Create email confirmation token."""
    token = secrets.token_hex(16)
    expires = datetime.utcnow() + timedelta(hours=24)
    db = get_db()
    db.email_confirmation_tokens.insert(
        user_id=user_id,
        token=token,
        expires_at=expires,
    )
    db.commit()
    return token, expires


def validate_email_token(token: str):
    """Validate email token, return user_id or None."""
    db = get_db()
    record = (
        db(
            (db.email_confirmation_tokens.token == token)
            & (db.email_confirmation_tokens.expires_at > datetime.utcnow())
            & (db.email_confirmation_tokens.confirmed_at is None)
        )
        .select()
        .first()
    )
    return record["user_id"] if record else None


def confirm_email(token: str) -> bool:
    """Mark email as confirmed."""
    db = get_db()
    db(db.email_confirmation_tokens.token == token).update(
        confirmed_at=datetime.utcnow()
    )
    db.commit()
    return True


# API keys
def create_api_key(user_id: int, name: str, scopes: str = "") -> tuple[str, str]:
    """Create API key. Returns (full_key, key_id)."""
    prefix = "pk_live" if not current_app.config.get("DEBUG") else "pk_test"
    key = f"{prefix}_{secrets.token_hex(16)}"
    key_hash = hashlib.sha256(key.encode()).hexdigest()

    db = get_db()
    key_id = db.api_keys.insert(
        user_id=user_id,
        name=name,
        key_hash=key_hash,
        prefix=prefix,
        scopes=scopes or "",
        is_active=True,
    )
    db.commit()
    return key, str(key_id)


def validate_api_key(key: str):
    """Validate API key, return key record or None."""
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    db = get_db()
    record = (
        db((db.api_keys.key_hash == key_hash) & (db.api_keys.is_active))
        .select()
        .first()
    )
    if record:
        db(db.api_keys.id == record.id).update(last_used_at=datetime.utcnow())
        db.commit()
        return record.as_dict() if record else None
    return None


def revoke_api_key(key_id: int, user_id: int) -> bool:
    """Revoke an API key."""
    db = get_db()
    updated = db((db.api_keys.id == key_id) & (db.api_keys.user_id == user_id)).update(
        is_active=False
    )
    db.commit()
    return updated > 0


def get_user_api_keys(user_id: int) -> list:
    """List API keys for user (without full key)."""
    db = get_db()
    keys = db(db.api_keys.user_id == user_id).select(orderby=~db.api_keys.created_at)
    return [
        {
            "id": k.id,
            "name": k.name,
            "prefix": k.prefix,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            "created_at": k.created_at.isoformat() if k.created_at else None,
        }
        for k in keys
    ]


# Audit logging
def audit_log(
    action: str,
    resource_type: str = None,
    resource_id: str = None,
    metadata: dict = None,
    user_id: int = None,
):
    """Log an audit event."""
    db = get_db()
    db.audit_logs.insert(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=request.remote_addr if request else None,
        user_agent=request.headers.get("User-Agent") if request else None,
        metadata=json.dumps(metadata) if metadata else None,
    )
    db.commit()


def get_audit_logs(limit: int = 100) -> list:
    """Get recent audit logs."""
    db = get_db()
    logs = db(db.audit_logs).select(
        orderby=~db.audit_logs.created_at,
        limitby=(0, limit),
    )
    return [
        {
            "id": log.id,
            "user_id": log.user_id,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


# Session management
def get_user_sessions(user_id: int) -> list:
    """List active sessions (refresh tokens) for user."""
    db = get_db()
    tokens = db(
        (db.refresh_tokens.user_id == user_id)
        & (db.refresh_tokens.revoked is False)
        & (db.refresh_tokens.expires_at > datetime.utcnow())
    ).select(orderby=~db.refresh_tokens.created_at)
    return [
        {
            "id": t.id,
            "device_info": t.device_info or "",
            "ip_address": t.ip_address or "",
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "expires_at": t.expires_at.isoformat() if t.expires_at else None,
        }
        for t in tokens
    ]


def revoke_session(session_id: int, user_id: int) -> bool:
    """Revoke a user session."""
    db = get_db()
    updated = db(
        (db.refresh_tokens.id == session_id) & (db.refresh_tokens.user_id == user_id)
    ).update(revoked=True)
    db.commit()
    return updated > 0
