"""SQLAlchemy Schema Models (for Alembic migrations and schema definition only).

DO NOT use these for runtime queries — use penguin-dal AsyncDB instead.
See models.py for runtime operations.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase

# Enumerated columns are String, not SQLAlchemy Enum, and deliberately.
#
# `Enum(PyEnum)` persists the MEMBER NAME ("CUSTOMER") on most backends and
# emits a native CREATE TYPE on PostgreSQL, while this migration declares
# String(50) and penguin-dal writes the lowercase VALUE at runtime. Those
# three disagreed: the ORM would have produced a native pg enum whose labels
# ("PROVIDER") no runtime write ever matches, so every insert raises on
# PostgreSQL while passing on SQLite. String + a CHECK constraint keeps the
# ORM, the migration and the runtime writing exactly the same bytes, and
# leaves the allowed set enforced by the database rather than by convention.

#: Allowed values for tenants.kind. Mirrors models.VALID_TENANT_KINDS.
TENANT_KINDS: tuple[str, ...] = ("provider", "customer")

#: Allowed values for product_tenant_map.external_kind.
#: Mirrors models.VALID_EXTERNAL_KINDS.
PRODUCT_EXTERNAL_KINDS: tuple[str, ...] = (
    "tenant_id",
    "organization_id",
    "namespace",
)


def _in_values(column: str, values: tuple[str, ...]) -> str:
    """Render an IN (...) CHECK expression for an enumerated text column."""
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({rendered})"


class Base(DeclarativeBase):
    """Declarative base for every schema model in this module.

    SQLAlchemy 2.0's typed DeclarativeBase, not the legacy untyped
    declarative_base() factory — the latter forced a per-class typing
    suppression on every subclass below.
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
    plan_tier = Column(String(50), default="free", server_default="free", nullable=False)
    license_key = Column(String(255))
    # server_default, not just a Python-side default: penguin-dal issues its
    # own INSERTs at runtime and never applies SQLAlchemy's Python defaults,
    # so a Python-only default leaves these NULL and every quota comparison
    # (`count >= None`) raises TypeError.
    max_users = Column(Integer, default=10, server_default=text("10"), nullable=False)
    max_products = Column(Integer, default=5, server_default=text("5"), nullable=False)
    settings = Column(Text)
    is_active = Column(Boolean, default=True, server_default=text("1"), nullable=False)
    # Hierarchical tenancy columns
    parent_tenant_id: Any = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    kind: Any = Column(
        String(50),
        default="customer",
        server_default="customer",
        nullable=False,
    )
    depth: Any = Column(Integer, default=0, server_default=text("0"), nullable=False)
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

    # Every hierarchy walk (both recursive CTEs, and the direct-children
    # query behind depth recomputation) filters on parent_tenant_id; without
    # an index each level of the recursion is a full table scan.
    __table_args__ = (
        Index("ix_tenants_parent_tenant_id", "parent_tenant_id"),
        CheckConstraint(_in_values("kind", TENANT_KINDS), name="ck_tenants_kind"),
    )


class TenantMember(Base):
    """Tenant membership."""

    __tablename__ = "tenant_members"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(50), default="member", server_default="member", nullable=False)
    invited_by_id = Column(Integer, ForeignKey("users.id"))
    joined_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)


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
    auth_type = Column(String(50), default="bearer", server_default="bearer", nullable=False)
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


class TeamInvitation(Base):
    """Pending team invitation, resolved by token.

    Was referenced at runtime by app.teams (send_invitation/accept_
    invitation/cancel_invitation via db.team_invitations) with no backing
    table anywhere in this schema, so every call raised AttributeError --
    see the fix/team-invitations branch. Shape mirrors PasswordResetToken/
    EmailConfirmationToken's token+expiry+resolved-at pattern; accepted_at
    plays the role used_at/confirmed_at play there.
    """

    __tablename__ = "team_invitations"
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    email = Column(String(255), nullable=False)
    role = Column(String(50), default="member", server_default="member", nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    invited_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime)
    created_at = Column(
        DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False
    )


class OAuthConnection(Base):
    """OAuth provider connection.

    access_token/refresh_token are stored as Fernet ciphertext (see
    app/encryption.py) -- app/models.py encrypts before every write. The
    column type stays Text; encryption is a value-level concern, not a
    schema-level one, matching product_connections.api_key/api_secret.
    """

    __tablename__ = "oauth_connections"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    provider = Column(String(50), nullable=False)
    provider_user_id = Column(String(255), nullable=False)
    access_token = Column(Text)
    refresh_token = Column(Text)
    # Nullable: not every provider token response includes expires_in, so
    # app/oauth.py only sets this when the provider reports one. Consumed
    # by a future token-refresh flow (refresh_token exists precisely to
    # renew an expired access_token, which requires knowing when it
    # expires) and surfaced read-only via GET /auth/oauth/connections.
    # Previously accepted as a kwarg by models.store_oauth_connection with
    # no backing column -- SQLAlchemy's compiler raised "Unconsumed column
    # names: expires_at" on every insert/update, 500ing every OAuth
    # sign-in that reached this call (new user, email-linked, or
    # provider-id-linked). This column, plus alembic/versions/
    # b3f2a9d1e6c4, closes that gap.
    expires_at = Column(DateTime, nullable=True)
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


class ProductTenantMap(Base):
    """Product tenant external mapping."""

    __tablename__ = "product_tenant_map"
    id = Column(Integer, primary_key=True)
    connection_id = Column(Integer, ForeignKey("product_connections.id"), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    external_kind: Any = Column(String(50), nullable=False)
    external_id = Column(String(255), nullable=False)
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

    __table_args__ = (
        CheckConstraint(
            _in_values("external_kind", PRODUCT_EXTERNAL_KINDS),
            name="ck_product_tenant_map_external_kind",
        ),
    )
