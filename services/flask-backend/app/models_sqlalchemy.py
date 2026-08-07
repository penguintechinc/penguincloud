"""SQLAlchemy Schema Models (for Alembic migrations and schema definition only).

DO NOT use these for runtime queries — use penguin-dal AsyncDB instead.
See models.py for runtime operations.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for every schema model in this module.

    SQLAlchemy 2.0's typed DeclarativeBase, not the legacy untyped
    declarative_base() factory — the latter forced a
    `type: ignore[valid-type,misc]` on every subclass below.
    """


class User(Base):
    """User account."""

    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role = Column(String(50), default="viewer", server_default="viewer", nullable=False)
    is_active = Column(Boolean, default=True, server_default=text("1"), nullable=False)
    created_at = Column(
        DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )


class RefreshToken(Base):
    """Refresh token for invalidation."""

    __tablename__ = "refresh_tokens"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False, server_default=text("0"), nullable=False)
    created_at = Column(
        DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False
    )


class MfaSecret(Base):
    """MFA TOTP secret."""

    __tablename__ = "mfa_secrets"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    secret = Column(String(255), nullable=False)
    backup_codes = Column(Text)
    enabled_at = Column(DateTime)
    created_at = Column(
        DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False
    )


class Tenant(Base):
    """Tenant (workspace)."""

    __tablename__ = "tenants"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(63), unique=True, nullable=False)
    display_name = Column(String(255))
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan_tier = Column(
        String(50), default="free", server_default="free", nullable=False
    )
    license_key = Column(String(255))
    max_users = Column(Integer, default=10)
    max_products = Column(Integer, default=5)
    settings = Column(Text)
    is_active = Column(Boolean, default=True, server_default=text("1"), nullable=False)
    created_at = Column(
        DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )


class TenantMember(Base):
    """Tenant membership."""

    __tablename__ = "tenant_members"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(50), default="member", server_default="member", nullable=False)
    invited_by_id = Column(Integer, ForeignKey("users.id"))
    joined_at = Column(
        DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False
    )


class ProductConnection(Base):
    """Product connection."""

    __tablename__ = "product_connections"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    product_type = Column(String(50), nullable=False)
    display_name = Column(String(255), nullable=False)
    base_url = Column(String(500), nullable=False)
    api_key = Column(Text)
    api_secret = Column(Text)
    auth_type = Column(
        String(50), default="bearer", server_default="bearer", nullable=False
    )
    health_endpoint = Column(String(255), default="/healthz")
    api_version = Column(String(20), default="v1")
    is_active = Column(Boolean, default=True, server_default=text("1"), nullable=False)
    last_health_check = Column(DateTime)
    health_status = Column(String(50), default="unknown")
    discovered = Column(Boolean, default=False)
    metadata_json = Column(Text)
    created_at = Column(
        DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )


class TenantProductFeature(Base):
    """Tenant product feature flag."""

    __tablename__ = "tenant_product_features"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    product_type = Column(String(50), nullable=False)
    feature_name = Column(String(255), nullable=False)
    enabled = Column(Boolean, default=True, server_default=text("1"), nullable=False)
    limits = Column(Text)


class Team(Base):
    """Team."""

    __tablename__ = "teams"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(63), unique=True, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TeamMember(Base):
    """Team membership."""

    __tablename__ = "team_members"
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(50), default="member", server_default="member", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class OAuthConnection(Base):
    """OAuth provider connection."""

    __tablename__ = "oauth_connections"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    provider = Column(String(50), nullable=False)
    provider_user_id = Column(String(255), nullable=False)
    access_token = Column(Text)
    refresh_token = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLog(Base):
    """Audit log entry."""

    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action_type = Column(String(100), nullable=False)
    resource_type = Column(String(100))
    resource_id = Column(String(255))
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    product_connection_id = Column(Integer, ForeignKey("product_connections.id"))
    request_body = Column(Text)
    response_status = Column(Integer)
    ip_address = Column(String(45))
    user_agent = Column(Text)
    metadata_json = Column(Text, name="metadata")
    created_at = Column(DateTime, default=datetime.utcnow)


class PasswordResetToken(Base):
    """Password reset token."""

    __tablename__ = "password_reset_tokens"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class EmailConfirmationToken(Base):
    """Email confirmation token."""

    __tablename__ = "email_confirmation_tokens"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    confirmed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class APIKey(Base):
    """API key."""

    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    key_hash = Column(String(255), unique=True, nullable=False)
    key_prefix = Column(String(50))
    last_used_at = Column(DateTime)
    expires_at = Column(DateTime)
    scopes = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
