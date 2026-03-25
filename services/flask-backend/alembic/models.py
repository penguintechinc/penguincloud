"""SQLAlchemy Models for Alembic Migrations (minimal to avoid Flask dependencies)."""

from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Boolean, ForeignKey, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    """User model for schema definition."""

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


class RefreshToken(Base):
    """RefreshToken model for schema definition."""

    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class MfaSecret(Base):
    """MfaSecret model for schema definition."""

    __tablename__ = "mfa_secrets"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    secret = Column(String(255), nullable=False)
    backup_codes = Column(Text)  # JSON array of backup codes
    enabled_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PasswordResetToken(Base):
    """PasswordResetToken model for schema definition."""

    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class EmailConfirmationToken(Base):
    """EmailConfirmationToken model for schema definition."""

    __tablename__ = "email_confirmation_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    confirmed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ApiKey(Base):
    """ApiKey model for schema definition."""

    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    key_hash = Column(String(255), unique=True, nullable=False)
    prefix = Column(String(50))
    last_used_at = Column(DateTime)
    expires_at = Column(DateTime)
    scopes = Column(Text)  # JSON array of scopes
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AuditLog(Base):
    """AuditLog model for schema definition."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(100), nullable=False)
    resource_type = Column(String(100))
    resource_id = Column(String(255))
    ip_address = Column(String(45))
    user_agent = Column(Text)
    meta = Column(
        Text, name="metadata"
    )  # JSON metadata (use 'meta' attribute, 'metadata' column)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
