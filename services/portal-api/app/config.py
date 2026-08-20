"""Quart Backend Configuration."""

import os
import tempfile
from datetime import timedelta

#: Reserved ``tenant`` claim value for a token minted before the user has
#: selected an active tenant. penguin-aaa's ``Claims`` model rejects an empty
#: tenant outright, and the house standard requires the claim on every token,
#: so an explicit sentinel carries "authenticated but not tenant-scoped"
#: instead. ``middleware.get_current_tenant_id`` maps it back to ``None`` so
#: tenant-gated routes still refuse it.
UNSCOPED_TENANT = "_unscoped"

#: The SECRET_KEY value assigned when the operator has not set SECRET_KEY at
#: all. This is a KNOWN, PUBLIC string committed to this repository's own
#: source — Quart signs the session cookie (itsdangerous) with SECRET_KEY,
#: and app/oauth.py's ``oauth_state`` CSRF check lives entirely inside that
#: signed session, so a deployment left on this default is as forgeable as
#: a session with no signature at all. Kept as a real (if insecure) string,
#: never "", so Quart's session machinery never sees an empty secret_key,
#: which behaves differently — and worse, silently — than a wrong one.
#: app/__init__.py's create_app() refuses to start outside TESTING while
#: SECRET_KEY still equals this sentinel; see its docstring.
#: (ruff S105 pattern-matches the NAME "INSECURE_DEFAULT_SECRET_KEY" as a
#: possible hardcoded password; the whole point of this constant is that
#: it is a known, public, non-secret value, not an actual credential.)
INSECURE_DEFAULT_SECRET_KEY = "dev-secret-key-change-in-production"  # noqa: S105


class Config:
    """Base configuration."""

    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", INSECURE_DEFAULT_SECRET_KEY)
    DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    # JWT
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "30")))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=int(os.getenv("JWT_REFRESH_TOKEN_DAYS", "7")))

    # OIDC provider (penguin-aaa). The issuer must be a fully-qualified URL —
    # penguin-aaa's validate_https_url() requires HTTPS for any non-localhost
    # host, so an opaque string like "penguincloud" is rejected at startup.
    JWT_ISSUER = os.getenv("JWT_ISSUER", "https://penguincloud.localhost.local")
    JWT_AUDIENCES = [
        a.strip() for a in os.getenv("JWT_AUDIENCES", "penguincloud-portal").split(",") if a.strip()
    ]
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "RS256")
    # Path for the persistent signing keystore. Unset (the default) selects an
    # in-process MemoryKeyStore, whose keys die with the worker — acceptable
    # for tests/dev, never for a multi-replica deployment where every replica
    # would otherwise sign with a key the others cannot verify. See
    # DEPLOYMENT_REPLICAS below: app/__init__.py:_build_oidc_provider refuses
    # to start rather than silently make that fallback when the operator has
    # declared more than one replica.
    JWT_KEYSTORE_PATH = os.getenv("JWT_KEYSTORE_PATH", "")
    # How many replicas of THIS service the operator/chart intends to run.
    # Declared, not detected: Kubernetes gives a pod no reliable in-process
    # signal for "how many siblings does my ReplicaSet have" (the Downward
    # API exposes this pod's own identity, never the replica count), so
    # rather than guess, the deployment states it — mirroring the chart's
    # own `replicaCount` value (see docs/DEVELOPMENT.md: "JWT Signing
    # Keystore"). Defaults to 1: a lone process never has a cross-replica
    # verification problem, so `make test-api`, docker-compose and a solo
    # dev server are unaffected unless this is explicitly raised.
    DEPLOYMENT_REPLICAS = int(os.getenv("DEPLOYMENT_REPLICAS", "1"))

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
            "authorization_url": ("https://login.microsoftonline.com/common/oauth2/v2.0/authorize"),
            "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            "userinfo_url": "https://graph.microsoft.com/v1.0/me",
        },
        "okta": {
            "client_id": os.getenv("OAUTH_OKTA_CLIENT_ID", ""),
            "client_secret": os.getenv("OAUTH_OKTA_CLIENT_SECRET", ""),
            "tenant_url": os.getenv("OAUTH_OKTA_TENANT_URL", "https://dev-12345.okta.com"),
            "authorization_url": "{tenant_url}/oauth2/v1/authorize",
            "token_url": "{tenant_url}/oauth2/v1/token",
            "userinfo_url": "{tenant_url}/oauth2/v1/userinfo",
        },
    }

    # License Configuration
    LICENSE_KEY = os.getenv("LICENSE_KEY", "")
    LICENSE_SERVER_URL = os.getenv("LICENSE_SERVER_URL", "https://license.penguintech.io")
    PRODUCT_NAME = os.getenv("PRODUCT_NAME", "project-template")
    RELEASE_MODE = os.getenv("RELEASE_MODE", "false").lower() == "true"

    # PenguinCloud Configuration
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")
    DISCOVERY_RANGES = os.getenv("DISCOVERY_RANGES", "")  # Comma-separated host list

    # Cache (Valkey/Redis-protocol) - backend-database.md CACHE_* convention.
    # Optional: the health poller (app/health_poller.py, Phase 6) degrades to
    # a per-worker in-memory fallback when CACHE_HOST is unset or the store
    # is unreachable - see app/health_cache.py.
    CACHE_HOST = os.getenv("CACHE_HOST", "")
    CACHE_PORT = int(os.getenv("CACHE_PORT", "6379"))
    CACHE_DB = int(os.getenv("CACHE_DB", "0"))
    CACHE_PASS = os.getenv("CACHE_PASS", "")
    CACHE_SSL = os.getenv("CACHE_SSL", "false").lower() == "true"

    # Health poller (Phase 6 - replaces the deleted go-backend health sweep).
    # Poll interval/jitter/timeout/concurrency are NOT here: they are fixed
    # requirements (15s ±20% jitter, 10s per-call timeout, Semaphore(50) --
    # see app/health_poller.py module constants), not deployment-tunable
    # knobs, so making them env vars would be configuration nothing reads.
    HEALTH_POLL_CACHE_TTL_SECONDS = int(os.getenv("HEALTH_POLL_CACHE_TTL_SECONDS", "60"))
    HEALTH_METRICS_PORT = int(os.getenv("HEALTH_METRICS_PORT", "9090"))

    # KillKrill Configuration
    KILLKRILL_ENABLED = os.getenv("KILLKRILL_ENABLED", "true").lower() == "true"
    KILLKRILL_API_URL = os.getenv("KILLKRILL_API_URL", "http://killkrill-receiver:8081")
    KILLKRILL_GRPC_URL = os.getenv("KILLKRILL_GRPC_URL", "killkrill-receiver:50051")
    KILLKRILL_CLIENT_ID = os.getenv("KILLKRILL_CLIENT_ID", "")
    KILLKRILL_CLIENT_SECRET = os.getenv("KILLKRILL_CLIENT_SECRET", "")

    @classmethod
    def get_db_uri(cls) -> str:
        """Build penguin-dal compatible database URI."""
        db_type = cls.DB_TYPE

        # Map common aliases to penguin-dal format
        type_map = {
            "postgresql": "postgres",
            "mysql": "mysql",
            "sqlite": "sqlite",
            "mssql": "mssql",
        }
        db_type = type_map.get(db_type, db_type)

        if db_type == "sqlite":
            # Handle both bare names (app_db) and full paths (/tmp/test.db)
            db_path = cls.DB_NAME
            if not db_path.endswith(".db"):
                db_path = f"{db_path}.db"
            return f"sqlite:///{db_path}"

        return f"{db_type}://{cls.DB_USER}:{cls.DB_PASS}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"


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

    # JWT Configuration for testing
    JWT_ISSUER = "https://penguincloud-test.localhost.local"
    JWT_AUDIENCES = ["penguincloud-test-client"]
