"""Database Models (SQLAlchemy for schema, PyDAL for runtime)."""

from datetime import datetime
from typing import Optional

from flask import Flask, g
from pydal import DAL, Field
from pydal.validators import IS_EMAIL, IS_IN_SET, IS_NOT_EMPTY
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base

from .config import Config

# SQLAlchemy ORM Base for migration support
Base = declarative_base()

# Valid roles for the application
VALID_ROLES = ["admin", "maintainer", "viewer"]

# Valid tenant plans
VALID_PLANS = ["free", "starter", "business", "enterprise"]

# Valid tenant member roles
VALID_TENANT_ROLES = ["owner", "admin", "member", "viewer"]

# Valid product auth types
VALID_AUTH_TYPES = ["bearer", "basic", "api_key", "none"]

# Valid health statuses
VALID_HEALTH_STATUSES = ["healthy", "degraded", "unhealthy", "unknown"]

# Product type enumeration — all PenguinTech products
PRODUCT_TYPES = [
    "marchproxy", "squawk", "license_server", "skauswatch", "waddleai",
    "articdbm", "cerberus", "waddlebot", "waddleperf", "iceshelves",
    "icecharts", "killkrill", "tobogganing", "nest", "darwin",
    "gough", "current", "elder", "admin", "generic",
]

# Product categories for UI organization
PRODUCT_CATEGORIES = {
    "infrastructure": ["marchproxy", "squawk", "articdbm", "iceshelves"],
    "security": ["skauswatch", "cerberus"],
    "ai": ["waddleai", "waddlebot"],
    "monitoring": ["waddleperf", "icecharts"],
    "operations": ["killkrill", "tobogganing", "darwin", "gough", "current", "license_server"],
    "development": ["nest"],
    "legacy": ["elder"],
    "administration": ["admin"],
}


# SQLAlchemy ORM Models (for schema definition and Alembic migrations)
class SQLAUser(Base):
    """SQLAlchemy User model for schema definition."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role = Column(String(50), default="viewer", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class SQLARefreshToken(Base):
    """SQLAlchemy RefreshToken model for schema definition."""

    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SQLAMfaSecret(Base):
    """SQLAlchemy MfaSecret model for schema definition."""

    __tablename__ = "mfa_secrets"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    secret = Column(String(255), nullable=False)
    backup_codes = Column(Text)  # JSON array of backup codes
    enabled_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SQLATenant(Base):
    """SQLAlchemy Tenant model for schema definition."""

    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(63), unique=True, nullable=False)
    display_name = Column(String(255))
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan = Column(String(50), default="free", nullable=False)
    license_key = Column(String(255))
    max_users = Column(Integer, default=10)
    max_products = Column(Integer, default=5)
    settings = Column(Text)  # JSON
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class SQLATenantMember(Base):
    """SQLAlchemy TenantMember model for schema definition."""

    __tablename__ = "tenant_members"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(50), default="member", nullable=False)
    invited_by_id = Column(Integer, ForeignKey("users.id"))
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SQLAProductConnection(Base):
    """SQLAlchemy ProductConnection model for schema definition."""

    __tablename__ = "product_connections"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    product_type = Column(String(50), nullable=False)
    display_name = Column(String(255), nullable=False)
    base_url = Column(String(500), nullable=False)
    api_key = Column(Text)  # Encrypted
    api_secret = Column(Text)  # Encrypted
    auth_type = Column(String(50), default="bearer", nullable=False)
    health_endpoint = Column(String(255), default="/healthz")
    api_version = Column(String(20), default="v1")
    is_active = Column(Boolean, default=True, nullable=False)
    last_health_check = Column(DateTime)
    health_status = Column(String(50), default="unknown")
    discovered = Column(Boolean, default=False)
    metadata_json = Column(Text)  # JSON
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class SQLATenantProductFeature(Base):
    """SQLAlchemy TenantProductFeature model for schema definition."""

    __tablename__ = "tenant_product_features"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    product_type = Column(String(50), nullable=False)
    feature_name = Column(String(255), nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    limits = Column(Text)  # JSON


def init_db(app: Flask) -> DAL:
    """Initialize database connection and define tables."""
    db_uri = Config.get_db_uri()

    db = DAL(
        db_uri,
        pool_size=Config.DB_POOL_SIZE,
        migrate=True,
        check_reserved=["all"],
        lazy_tables=False,
    )

    # Define users table
    db.define_table(
        "users",
        Field(
            "email",
            "string",
            length=255,
            unique=True,
            requires=[
                IS_NOT_EMPTY(error_message="Email is required"),
                IS_EMAIL(error_message="Invalid email format"),
            ],
        ),
        Field("password_hash", "string", length=255, requires=IS_NOT_EMPTY()),
        Field("full_name", "string", length=255),
        Field(
            "role",
            "string",
            length=50,
            default="viewer",
            requires=IS_IN_SET(
                VALID_ROLES,
                error_message=f"Role must be one of: {', '.join(VALID_ROLES)}",
            ),
        ),
        Field("is_active", "boolean", default=True),
        Field("created_at", "datetime", default=datetime.utcnow),
        Field(
            "updated_at", "datetime", default=datetime.utcnow, update=datetime.utcnow
        ),
    )

    # Define refresh tokens table for token invalidation
    db.define_table(
        "refresh_tokens",
        Field("user_id", "reference users", requires=IS_NOT_EMPTY()),
        Field("token_hash", "string", length=255, unique=True),
        Field("expires_at", "datetime"),
        Field("revoked", "boolean", default=False),
        Field("created_at", "datetime", default=datetime.utcnow),
    )

    # Define MFA secrets table for TOTP 2FA
    db.define_table(
        "mfa_secrets",
        Field("user_id", "reference users", requires=IS_NOT_EMPTY(), unique=True),
        Field("secret", "string", length=255, requires=IS_NOT_EMPTY()),
        Field("backup_codes", "text"),  # JSON array of backup codes
        Field("enabled_at", "datetime"),
        Field("created_at", "datetime", default=datetime.utcnow),
    )

    # Password reset tokens
    db.define_table(
        "password_reset_tokens",
        Field("user_id", "reference users", requires=IS_NOT_EMPTY()),
        Field("token", "string", length=255, unique=True, requires=IS_NOT_EMPTY()),
        Field("expires_at", "datetime"),
        Field("used_at", "datetime"),
        Field("created_at", "datetime", default=datetime.utcnow),
    )

    # Email confirmation tokens
    db.define_table(
        "email_confirmation_tokens",
        Field("user_id", "reference users", requires=IS_NOT_EMPTY()),
        Field("token", "string", length=255, unique=True, requires=IS_NOT_EMPTY()),
        Field("expires_at", "datetime"),
        Field("confirmed_at", "datetime"),
        Field("created_at", "datetime", default=datetime.utcnow),
    )

    # API keys
    db.define_table(
        "api_keys",
        Field("user_id", "reference users", requires=IS_NOT_EMPTY()),
        Field("name", "string", length=255, requires=IS_NOT_EMPTY()),
        Field("key_hash", "string", length=255, unique=True, requires=IS_NOT_EMPTY()),
        Field("prefix", "string", length=50),
        Field("last_used_at", "datetime"),
        Field("expires_at", "datetime"),
        Field("scopes", "text"),
        Field("is_active", "boolean", default=True),
        Field("created_at", "datetime", default=datetime.utcnow),
    )

    # Tenants table
    db.define_table(
        "tenants",
        Field("name", "string", length=255, requires=IS_NOT_EMPTY()),
        Field("slug", "string", length=63, unique=True, requires=IS_NOT_EMPTY()),
        Field("display_name", "string", length=255),
        Field("owner_id", "reference users", requires=IS_NOT_EMPTY()),
        Field(
            "plan", "string", length=50, default="free",
            requires=IS_IN_SET(VALID_PLANS),
        ),
        Field("license_key", "string", length=255),
        Field("max_users", "integer", default=10),
        Field("max_products", "integer", default=5),
        Field("settings", "text"),  # JSON
        Field("is_active", "boolean", default=True),
        Field("created_at", "datetime", default=datetime.utcnow),
        Field("updated_at", "datetime", default=datetime.utcnow, update=datetime.utcnow),
    )

    # Tenant members table
    db.define_table(
        "tenant_members",
        Field("tenant_id", "reference tenants", requires=IS_NOT_EMPTY()),
        Field("user_id", "reference users", requires=IS_NOT_EMPTY()),
        Field(
            "role", "string", length=50, default="member",
            requires=IS_IN_SET(VALID_TENANT_ROLES),
        ),
        Field("invited_by_id", "reference users"),
        Field("joined_at", "datetime", default=datetime.utcnow),
    )

    # Product connections table
    db.define_table(
        "product_connections",
        Field("tenant_id", "reference tenants", requires=IS_NOT_EMPTY()),
        Field(
            "product_type", "string", length=50,
            requires=IS_IN_SET(PRODUCT_TYPES),
        ),
        Field("display_name", "string", length=255, requires=IS_NOT_EMPTY()),
        Field("base_url", "string", length=500, requires=IS_NOT_EMPTY()),
        Field("api_key", "text"),  # Encrypted
        Field("api_secret", "text"),  # Encrypted
        Field(
            "auth_type", "string", length=50, default="bearer",
            requires=IS_IN_SET(VALID_AUTH_TYPES),
        ),
        Field("health_endpoint", "string", length=255, default="/healthz"),
        Field("api_version", "string", length=20, default="v1"),
        Field("is_active", "boolean", default=True),
        Field("last_health_check", "datetime"),
        Field(
            "health_status", "string", length=50, default="unknown",
            requires=IS_IN_SET(VALID_HEALTH_STATUSES),
        ),
        Field("discovered", "boolean", default=False),
        Field("metadata_json", "text"),  # JSON
        Field("created_at", "datetime", default=datetime.utcnow),
        Field("updated_at", "datetime", default=datetime.utcnow, update=datetime.utcnow),
    )

    # Tenant product features table
    db.define_table(
        "tenant_product_features",
        Field("tenant_id", "reference tenants", requires=IS_NOT_EMPTY()),
        Field("product_type", "string", length=50, requires=IS_IN_SET(PRODUCT_TYPES)),
        Field("feature_name", "string", length=255, requires=IS_NOT_EMPTY()),
        Field("enabled", "boolean", default=True),
        Field("limits", "text"),  # JSON
    )

    # Audit logs
    db.define_table(
        "audit_logs",
        Field("user_id", "reference users"),
        Field("action", "string", length=100, requires=IS_NOT_EMPTY()),
        Field("resource_type", "string", length=100),
        Field("resource_id", "string", length=255),
        Field("tenant_id", "reference tenants"),
        Field("product_connection_id", "reference product_connections"),
        Field("request_body", "text"),
        Field("response_status", "integer"),
        Field("ip_address", "string", length=45),
        Field("user_agent", "text"),
        Field("metadata", "text"),
        Field("created_at", "datetime", default=datetime.utcnow),
    )

    # Commit table definitions
    db.commit()

    # Store db instance in app
    app.config["db"] = db

    return db


def get_db() -> DAL:
    """Get database connection for current request context."""
    from flask import current_app

    if "db" not in g:
        g.db = current_app.config.get("db")
    return g.db


def get_user_by_email(email: str) -> Optional[dict]:
    """Get user by email address."""
    db = get_db()
    user = db(db.users.email == email).select().first()
    return user.as_dict() if user else None


def get_user_by_id(user_id: int) -> Optional[dict]:
    """Get user by ID."""
    db = get_db()
    user = db(db.users.id == user_id).select().first()
    return user.as_dict() if user else None


def create_user(
    email: str, password_hash: str, full_name: str = "", role: str = "viewer"
) -> dict:
    """Create a new user."""
    db = get_db()
    user_id = db.users.insert(
        email=email,
        password_hash=password_hash,
        full_name=full_name,
        role=role,
        is_active=True,
    )
    db.commit()
    return get_user_by_id(user_id)


def update_user(user_id: int, **kwargs) -> Optional[dict]:
    """Update user by ID."""
    db = get_db()

    # Filter allowed fields
    allowed_fields = {"email", "password_hash", "full_name", "role", "is_active"}
    update_data = {k: v for k, v in kwargs.items() if k in allowed_fields}

    if not update_data:
        return get_user_by_id(user_id)

    db(db.users.id == user_id).update(**update_data)
    db.commit()
    return get_user_by_id(user_id)


def delete_user(user_id: int) -> bool:
    """Delete user by ID."""
    db = get_db()
    deleted = db(db.users.id == user_id).delete()
    db.commit()
    return deleted > 0


def list_users(page: int = 1, per_page: int = 20) -> tuple[list[dict], int]:
    """List users with pagination."""
    db = get_db()
    offset = (page - 1) * per_page

    users = db(db.users).select(
        orderby=db.users.created_at,
        limitby=(offset, offset + per_page),
    )
    total = db(db.users).count()

    return [u.as_dict() for u in users], total


def store_refresh_token(user_id: int, token_hash: str, expires_at: datetime) -> int:
    """Store a refresh token."""
    db = get_db()
    token_id = db.refresh_tokens.insert(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.commit()
    return token_id


def revoke_refresh_token(token_hash: str) -> bool:
    """Revoke a refresh token."""
    db = get_db()
    updated = db(db.refresh_tokens.token_hash == token_hash).update(revoked=True)
    db.commit()
    return updated > 0


def is_refresh_token_valid(token_hash: str) -> bool:
    """Check if refresh token is valid (not revoked and not expired)."""
    db = get_db()
    token = (
        db(
            (db.refresh_tokens.token_hash == token_hash)
            & (db.refresh_tokens.revoked is False)
            & (db.refresh_tokens.expires_at > datetime.utcnow())
        )
        .select()
        .first()
    )
    return token is not None


def revoke_all_user_tokens(user_id: int) -> int:
    """Revoke all refresh tokens for a user."""
    db = get_db()
    updated = db(db.refresh_tokens.user_id == user_id).update(revoked=True)
    db.commit()
    return updated


def create_mfa_secret(user_id: int, secret: str, backup_codes: str) -> dict:
    """Store MFA secret for user."""
    db = get_db()
    db.mfa_secrets.insert(
        user_id=user_id,
        secret=secret,
        backup_codes=backup_codes,
    )
    db.commit()
    return get_mfa_secret(user_id)


def get_mfa_secret(user_id: int) -> Optional[dict]:
    """Get MFA secret for user."""
    db = get_db()
    mfa = db(db.mfa_secrets.user_id == user_id).select().first()
    return mfa.as_dict() if mfa else None


def enable_mfa(user_id: int) -> bool:
    """Enable MFA for user."""
    db = get_db()
    updated = db(db.mfa_secrets.user_id == user_id).update(enabled_at=datetime.utcnow())
    db.commit()
    return updated > 0


def disable_mfa(user_id: int) -> bool:
    """Disable MFA for user."""
    db = get_db()
    deleted = db(db.mfa_secrets.user_id == user_id).delete()
    db.commit()
    return deleted > 0


def is_mfa_enabled(user_id: int) -> bool:
    """Check if MFA is enabled for user."""
    db = get_db()
    mfa = (
        db(
            (db.mfa_secrets.user_id == user_id)
            & (db.mfa_secrets.enabled_at is not None)
        )
        .select()
        .first()
    )
    return mfa is not None


# Tenant helper functions

def create_tenant(name: str, slug: str, owner_id: int, display_name: str = "",
                  plan: str = "free") -> dict:
    """Create a new tenant and add the owner as a member."""
    db = get_db()
    tenant_id = db.tenants.insert(
        name=name,
        slug=slug,
        display_name=display_name or name,
        owner_id=owner_id,
        plan=plan,
    )
    # Add owner as tenant member
    db.tenant_members.insert(
        tenant_id=tenant_id,
        user_id=owner_id,
        role="owner",
    )
    db.commit()
    return get_tenant_by_id(tenant_id)


def get_tenant_by_id(tenant_id: int) -> Optional[dict]:
    """Get tenant by ID."""
    db = get_db()
    tenant = db(db.tenants.id == tenant_id).select().first()
    return tenant.as_dict() if tenant else None


def get_tenant_by_slug(slug: str) -> Optional[dict]:
    """Get tenant by slug."""
    db = get_db()
    tenant = db(db.tenants.slug == slug).select().first()
    return tenant.as_dict() if tenant else None


def get_user_tenants(user_id: int) -> list[dict]:
    """Get all tenants a user is a member of."""
    db = get_db()
    memberships = db(db.tenant_members.user_id == user_id).select()
    tenant_ids = [m.tenant_id for m in memberships]
    if not tenant_ids:
        return []
    tenants = db(db.tenants.id.belongs(tenant_ids)).select()
    result = []
    for t in tenants:
        td = t.as_dict()
        membership = next((m for m in memberships if m.tenant_id == t.id), None)
        td["user_role"] = membership.role if membership else None
        result.append(td)
    return result


def get_user_tenant_role(user_id: int, tenant_id: int) -> Optional[str]:
    """Get user's role in a tenant."""
    db = get_db()
    member = db(
        (db.tenant_members.user_id == user_id)
        & (db.tenant_members.tenant_id == tenant_id)
    ).select().first()
    return member.role if member else None


def get_tenant_members(tenant_id: int) -> list[dict]:
    """Get all members of a tenant with user details."""
    db = get_db()
    members = db(db.tenant_members.tenant_id == tenant_id).select()
    result = []
    for m in members:
        md = m.as_dict()
        user = db(db.users.id == m.user_id).select().first()
        if user:
            md["user_email"] = user.email
            md["user_full_name"] = user.full_name
        result.append(md)
    return result


def add_tenant_member(tenant_id: int, user_id: int, role: str = "member",
                      invited_by_id: int = None) -> dict:
    """Add a member to a tenant."""
    db = get_db()
    member_id = db.tenant_members.insert(
        tenant_id=tenant_id,
        user_id=user_id,
        role=role,
        invited_by_id=invited_by_id,
    )
    db.commit()
    return db(db.tenant_members.id == member_id).select().first().as_dict()


def get_tenant_member_count(tenant_id: int) -> int:
    """Get the count of members in a tenant."""
    db = get_db()
    return db(db.tenant_members.tenant_id == tenant_id).count()


# Product connection helper functions

def create_product_connection(tenant_id: int, product_type: str, display_name: str,
                              base_url: str, auth_type: str = "bearer",
                              api_key: str = "", api_secret: str = "",
                              health_endpoint: str = "/healthz",
                              api_version: str = "v1",
                              discovered: bool = False) -> dict:
    """Create a new product connection."""
    from .encryption import encrypt_value
    db = get_db()
    conn_id = db.product_connections.insert(
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
        health_status="unknown",
    )
    db.commit()
    return get_product_connection_by_id(conn_id)


def get_product_connection_by_id(conn_id: int) -> Optional[dict]:
    """Get product connection by ID (without decrypting secrets)."""
    db = get_db()
    conn = db(db.product_connections.id == conn_id).select().first()
    if not conn:
        return None
    result = conn.as_dict()
    # Mask secrets in response
    result["api_key"] = "***" if result.get("api_key") else ""
    result["api_secret"] = "***" if result.get("api_secret") else ""
    return result


def get_product_connection_raw(conn_id: int) -> Optional[dict]:
    """Get product connection with encrypted secrets (for proxy use)."""
    db = get_db()
    conn = db(db.product_connections.id == conn_id).select().first()
    return conn.as_dict() if conn else None


def get_tenant_product_connections(tenant_id: int) -> list[dict]:
    """Get all product connections for a tenant."""
    db = get_db()
    connections = db(
        (db.product_connections.tenant_id == tenant_id)
        & (db.product_connections.is_active == True)
    ).select(orderby=db.product_connections.product_type)
    result = []
    for c in connections:
        cd = c.as_dict()
        cd["api_key"] = "***" if cd.get("api_key") else ""
        cd["api_secret"] = "***" if cd.get("api_secret") else ""
        result.append(cd)
    return result


def get_tenant_product_count(tenant_id: int) -> int:
    """Get the count of active product connections for a tenant."""
    db = get_db()
    return db(
        (db.product_connections.tenant_id == tenant_id)
        & (db.product_connections.is_active == True)
    ).count()


def update_product_health(conn_id: int, status: str) -> None:
    """Update health status of a product connection."""
    db = get_db()
    db(db.product_connections.id == conn_id).update(
        health_status=status,
        last_health_check=datetime.utcnow(),
    )
    db.commit()


def create_audit_log(user_id: int, action: str, resource_type: str = "",
                     resource_id: str = "", tenant_id: int = None,
                     product_connection_id: int = None,
                     request_body: str = "", response_status: int = None,
                     ip_address: str = "", user_agent: str = "",
                     metadata: str = "") -> int:
    """Create an audit log entry."""
    db = get_db()
    log_id = db.audit_logs.insert(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        tenant_id=tenant_id,
        product_connection_id=product_connection_id,
        request_body=request_body,
        response_status=response_status,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=metadata,
    )
    db.commit()
    return log_id
