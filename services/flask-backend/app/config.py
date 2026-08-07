"""Flask Backend Configuration."""

import os
import tempfile
from datetime import timedelta


class Config:
    """Base configuration."""

    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    # JWT
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "30"))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        days=int(os.getenv("JWT_REFRESH_TOKEN_DAYS", "7"))
    )

    # Database - PyDAL compatible
    DB_TYPE = os.getenv("DB_TYPE", "postgres")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "app_db")
    DB_USER = os.getenv("DB_USER", "app_user")
    DB_PASS = os.getenv("DB_PASS", "app_pass")
    DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))

    # CORS - comma-separated allowlist (parsed in app factory)
    CORS_ORIGINS_ENV = os.getenv("CORS_ORIGINS", "http://localhost:3000")

    # OAuth2/SSO Configuration
    OAUTH_ENABLED = os.getenv("OAUTH_ENABLED", "false").lower() == "true"
    OAUTH_PROVIDERS = {
        "google": {
            "client_id": os.getenv("OAUTH_GOOGLE_CLIENT_ID", ""),
            "client_secret": os.getenv("OAUTH_GOOGLE_CLIENT_SECRET", ""),
            "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        },
        "microsoft": {
            "client_id": os.getenv("OAUTH_MICROSOFT_CLIENT_ID", ""),
            "client_secret": os.getenv("OAUTH_MICROSOFT_CLIENT_SECRET", ""),
            "authorization_url": (
                "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
            ),
            "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            "userinfo_url": "https://graph.microsoft.com/v1.0/me",
        },
        "okta": {
            "client_id": os.getenv("OAUTH_OKTA_CLIENT_ID", ""),
            "client_secret": os.getenv("OAUTH_OKTA_CLIENT_SECRET", ""),
            "tenant_url": os.getenv(
                "OAUTH_OKTA_TENANT_URL", "https://dev-12345.okta.com"
            ),
            "authorization_url": "{tenant_url}/oauth2/v1/authorize",
            "token_url": "{tenant_url}/oauth2/v1/token",
            "userinfo_url": "{tenant_url}/oauth2/v1/userinfo",
        },
    }

    # License Configuration
    LICENSE_KEY = os.getenv("LICENSE_KEY", "")
    LICENSE_SERVER_URL = os.getenv(
        "LICENSE_SERVER_URL", "https://license.penguintech.io"
    )
    PRODUCT_NAME = os.getenv("PRODUCT_NAME", "project-template")
    RELEASE_MODE = os.getenv("RELEASE_MODE", "false").lower() == "true"

    # PenguinCloud Configuration
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")
    GO_HEALTH_GRPC_URL = os.getenv("GO_HEALTH_GRPC_URL", "go-backend:50052")
    DISCOVERY_RANGES = os.getenv("DISCOVERY_RANGES", "")  # Comma-separated host list

    # KillKrill Configuration
    KILLKRILL_ENABLED = os.getenv("KILLKRILL_ENABLED", "true").lower() == "true"
    KILLKRILL_API_URL = os.getenv("KILLKRILL_API_URL", "http://killkrill-receiver:8081")
    KILLKRILL_GRPC_URL = os.getenv("KILLKRILL_GRPC_URL", "killkrill-receiver:50051")
    KILLKRILL_CLIENT_ID = os.getenv("KILLKRILL_CLIENT_ID", "")
    KILLKRILL_CLIENT_SECRET = os.getenv("KILLKRILL_CLIENT_SECRET", "")

    @classmethod
    def get_db_uri(cls) -> str:
        """Build PyDAL-compatible database URI."""
        db_type = cls.DB_TYPE

        # Map common aliases to PyDAL format
        type_map = {
            "postgresql": "postgres",
            "mysql": "mysql",
            "sqlite": "sqlite",
            "mssql": "mssql",
        }
        db_type = type_map.get(db_type, db_type)

        if db_type == "sqlite":
            return f"sqlite://{cls.DB_NAME}.db"

        return (
            f"{db_type}://{cls.DB_USER}:{cls.DB_PASS}@"
            f"{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"
        )


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False


class TestingConfig(Config):
    """Testing configuration."""

    TESTING = True
    DB_TYPE = "sqlite"
    # File-based DB avoids the in-memory-per-connection pooling issue (see
    # models.init_db). The path is resolved once per process: TEST_DB_PATH
    # (set by tests/conftest.py at collection time, before any test module
    # is imported) takes precedence; otherwise a fresh tempfile.mkdtemp()
    # directory is used. Either way the path is unique per process, so
    # concurrent/repeated test runs never collide on or reuse a stale
    # shared path — unlike a hardcoded literal.
    DB_NAME = os.environ.get("TEST_DB_PATH") or os.path.join(
        tempfile.mkdtemp(prefix="penguincloud-test-"), "test.db"
    )
