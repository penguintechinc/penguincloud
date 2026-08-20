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
#: SECRET_KEY still resolves (after normalisation) to a PUBLISHED_INSECURE_
#: SECRET_KEY_VALUES member; see its docstring.
#: (ruff S105 pattern-matches the NAME "INSECURE_DEFAULT_SECRET_KEY" as a
#: possible hardcoded password; the whole point of this constant is that
#: it is a known, public, non-secret value, not an actual credential.)
INSECURE_DEFAULT_SECRET_KEY = "dev-secret-key-change-in-production"  # noqa: S105

#: Every SECRET_KEY literal this repository has ever published as a
#: fallback, denylisted together — NOT just this file's own default.
#: Round-1 review: an exact `!=` check against only
#: INSECURE_DEFAULT_SECRET_KEY missed docker-compose.yml's *different*
#: former fallback ("change-me-in-production"); this fix's own removal of
#: that fallback would otherwise have stranded every developer who
#: already had it in their `.env`/shell on a still-published key while
#: the new guard reported green — the commit creating the exact gap it
#: exists to close. A set, not a single sentinel, so a third published
#: default introduced anywhere else in the repo is one line to add here,
#: not a reason for the check to silently miss it again.
PUBLISHED_INSECURE_SECRET_KEY_VALUES = frozenset(
    {
        INSECURE_DEFAULT_SECRET_KEY,  # app/config.py's own default
        "change-me-in-production",  # docker-compose.yml's former default
    }
)

#: Floor, not a strength guarantee. Cheap to check, and costs a genuine
#: secret nothing — any reasonable generator (`secrets.token_hex()` is 64
#: chars; Django's default generator is 50) clears it by a wide margin.
#: What it rejects is the trivially-short/typed-by-hand class ("admin",
#: "test123", "" after normalisation) that an exact-match denylist alone
#: does not, without attempting fuzzy/entropy detection this fix
#: deliberately does not build (see app/__init__.py's
#: _require_configured_secret_key docstring for why that's out of scope).
MIN_SECRET_KEY_LENGTH = 32


def _declared_positive_int_env(name: str, default: int) -> tuple[int, bool]:
    """Parse a positive-int env var; return ``(value, was_explicitly_set)``.

    Round-1 review (M1/M2): the previous inline ``int(os.getenv(name,
    "1"))`` had two faults. First, an unparseable value (a typo'd
    ``DEPLOYMENT_REPLICAS=three``) raised a bare ``ValueError`` at module
    import — crashing pytest collection and ``scripts/export-openapi.py``
    with a message naming neither the variable nor the fix. Second, ``0``
    or a negative value parsed and was silently PERMITTED — a
    ``DEPLOYMENT_REPLICAS=0`` is nonsensical (there is always at least
    the process reading this config) and would have sailed through the
    ``> 1`` comparisons in app/__init__.py without ever refusing to
    start. Both are fixed here: the raised error is a ``ValueError``
    naming the exact variable, the value received, and the fix; and
    anything less than 1 is rejected the same way as unparseable input.

    The ``bool`` half of the return answers a DIFFERENT question this
    fix also needs: "did the operator say anything at all", distinct
    from "what value resulted". ``int(os.getenv(name, "1"))`` collapses
    unset and ``=1`` into the same observable state, which is exactly
    what let ``DEPLOYMENT_REPLICAS`` stay silently inert in every
    deployment that has never heard of the variable (round-1 I1) — the
    guard in app/__init__.py that reads this needs to tell "explicitly
    declared 1" apart from "said nothing, defaulted to 1" to fail closed
    on the latter.
    """
    raw = os.getenv(name)
    if raw is None:
        return default, False
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(
            f"{name}={raw!r} is not a valid integer. Unset it to use the "
            f"default ({default}), or set it to a positive whole number."
        ) from None
    if value < 1:
        raise ValueError(
            f"{name}={value} must be a positive integer (>= 1) — it "
            "declares how many processes of this kind exist, and zero or "
            "negative is not a valid count."
        )
    return value, True


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
    # for tests/dev, never for a genuinely multi-process deployment where
    # every process would otherwise sign with a key the others cannot
    # verify. See DEPLOYMENT_REPLICAS/HYPERCORN_WORKERS below:
    # app/__init__.py:_build_oidc_provider refuses to start rather than
    # silently make that fallback when the operator has declared more than
    # one process, OR when the operator has declared neither variable at
    # all (round-1 I1: undeclared must fail closed, not assume 1).
    JWT_KEYSTORE_PATH = os.getenv("JWT_KEYSTORE_PATH", "")
    # How many REPLICAS (pods) of THIS service the operator/chart intends
    # to run. Declared, not detected: Kubernetes gives a pod no reliable
    # in-process signal for "how many siblings does my ReplicaSet have"
    # (the Downward API exposes this pod's own identity, never the
    # replica count), so rather than guess, the deployment states it —
    # mirroring the chart's own `replicaCount` value (see
    # docs/DEVELOPMENT.md: "JWT Signing Keystore"). The paired ``_DECLARED``
    # boolean is what makes "declared 1" distinguishable from "said
    # nothing" — see _declared_positive_int_env's docstring.
    DEPLOYMENT_REPLICAS, DEPLOYMENT_REPLICAS_DECLARED = _declared_positive_int_env(
        "DEPLOYMENT_REPLICAS", 1
    )
    # How many hypercorn WORKER PROCESSES within a single replica/pod.
    # Same "declared, not detected" reasoning as DEPLOYMENT_REPLICAS, and
    # round-1 I3's whole point: the failure domain that matters is
    # PROCESSES, not replicas — `hypercorn --workers N` calls
    # create_app() once per worker, each building its own MemoryKeyStore,
    # which is the identical cross-verification failure on a single pod.
    # services/portal-api/Dockerfile's CMD reads this same variable (via
    # HYPERCORN_WORKERS, defaulted and exported to 1 there) so the
    # process count hypercorn actually launches and the count this guard
    # checks against can never drift apart.
    HYPERCORN_WORKERS, HYPERCORN_WORKERS_DECLARED = _declared_positive_int_env(
        "HYPERCORN_WORKERS", 1
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
    # Declared explicitly, not left to default-and-undeclared: the JWT
    # keystore guard (app/__init__.py:_build_oidc_provider) refuses to
    # start when NEITHER JWT_KEYSTORE_PATH nor an explicit replica/worker
    # count is declared (round-1 I1 — undeclared must fail closed, not
    # silently assume 1). Each pytest-created app genuinely IS one
    # declared single process, so it states that rather than relying on
    # Config's env-var default to happen to land on the right number.
    DEPLOYMENT_REPLICAS = 1
    DEPLOYMENT_REPLICAS_DECLARED = True
    HYPERCORN_WORKERS = 1
    HYPERCORN_WORKERS_DECLARED = True
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
