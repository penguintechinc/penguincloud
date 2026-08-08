"""Quart Backend Application Factory (async-native)."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

from penguin_aaa.authn.oidc_provider import OIDCProvider, OIDCProviderConfig
from penguin_dal.quart_ext import get_db, init_dal
from penguin_aaa.crypto.keystore import FileKeyStore, KeyStore, MemoryKeyStore
from quart import Quart
from quart_cors import cors
from quart_schema import HttpSecurityScheme, Info, QuartSchema

from .config import Config
from .killkrill import killkrill_manager
from .license import license_manager
from .middleware import setup_request_logging

log = logging.getLogger(__name__)


def _build_oidc_provider(app: Quart) -> OIDCProvider:
    """Build the penguin-aaa OIDC provider backing this app's tokens.

    Uses a FileKeyStore when JWT_KEYSTORE_PATH is configured so signing keys
    survive restarts and are shared across replicas; falls back to an
    in-process MemoryKeyStore for tests and single-process development.
    """
    algorithm: str = app.config["JWT_ALGORITHM"]
    keystore_path: str = app.config["JWT_KEYSTORE_PATH"]
    keystore: KeyStore = (
        FileKeyStore(Path(keystore_path), algorithm=algorithm)
        if keystore_path
        else MemoryKeyStore(algorithm=algorithm)
    )

    token_ttl = app.config["JWT_ACCESS_TOKEN_EXPIRES"]
    provider_config = OIDCProviderConfig(
        issuer=app.config["JWT_ISSUER"],
        audiences=list(app.config["JWT_AUDIENCES"]),
        algorithm=algorithm,
        token_ttl=token_ttl,
        # max_token_ttl is an upper bound penguin-aaa asserts token_ttl
        # against; keep it at or above the configured access-token lifetime
        # so a longer JWT_ACCESS_TOKEN_MINUTES doesn't fail app startup.
        max_token_ttl=max(token_ttl, timedelta(hours=1)),
        refresh_ttl=app.config["JWT_REFRESH_TOKEN_EXPIRES"],
    )
    return OIDCProvider(provider_config, keystore)


def create_app(config_class: type[Config] = Config) -> Quart:
    """Create and configure the Quart application.

    Note: Routes are async; the factory itself is sync.
    Database initialization happens at app startup (before_serving).
    """
    app = Quart(__name__)
    app.config.from_object(config_class)

    # Set session/cookie configuration
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    # Initialize QuartSchema for request/response validation and OpenAPI
    # generation.
    #
    # All four UI/spec paths are set to None on purpose. quart-schema mounts
    # /openapi.json, /docs, /redocs and /scalar UNAUTHENTICATED by default,
    # each serving the complete API surface — every path, parameter name and
    # request schema — to anyone who can reach the service. backend.md
    # requires the live spec behind the same JWT middleware as the API, with
    # only the login endpoint published in the clear. app/openapi.py mounts
    # the replacements: a public login-only document and an authenticated
    # full one. Leaving even one of these four enabled would keep an
    # anonymous copy of the full map at a URL nobody remembered.
    app.config["QUART_SCHEMA_CONVERT_CASING"] = False
    QuartSchema(
        app,
        openapi_path=None,
        swagger_ui_path=None,
        redoc_ui_path=None,
        scalar_ui_path=None,
        info=Info(title="PenguinCloud Portal API", version="1.0.0"),
        security_schemes={
            "bearerAuth": HttpSecurityScheme(scheme="bearer", bearer_format="JWT")
        },
        security=[{"bearerAuth": []}],
    )

    # Initialize CORS with explicit origin allowlist (security: no open CORS)
    origins_str = app.config.get("CORS_ORIGINS_ENV", "http://localhost:3000")
    allow_origins = [o.strip() for o in origins_str.split(",") if o.strip()]
    cors(
        app,
        allow_origin=allow_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Tenant-Scope"],
        allow_credentials=True,
    )

    # Initialize the OIDC token provider (penguin-aaa). Every token this app
    # issues or verifies goes through it, so failing to register it leaves
    # auth_required returning 500 on every protected route.
    app.extensions["oidc_provider"] = _build_oidc_provider(app)

    # Initialize database (penguin-dal AsyncDB) for immediate test availability
    try:
        db_uri = config_class.get_db_uri()
        init_dal(
            app,
            uri=db_uri,
            pool_size=app.config.get("DB_POOL_SIZE", 10),
            echo=app.config.get("DB_ECHO", False),
        )
        log.info(f"Database initialized: {db_uri}")
    except ValueError as e:
        log.error(f"Database initialization failed: {e}")
        raise

    # Validate license at startup
    @app.before_serving
    async def _init_license() -> None:
        """Validate license on application startup."""
        if not license_manager.validate():
            if app.config.get("RELEASE_MODE"):
                raise RuntimeError("License validation failed in RELEASE_MODE")
        log.info(f"License Status: {license_manager.get_status()}")

    # Initialize KillKrill at startup
    @app.before_serving
    async def _init_killkrill() -> None:
        """Initialize KillKrill on application startup."""
        killkrill_manager.setup(
            api_url=str(app.config.get("KILLKRILL_API_URL", "")),
            grpc_url=str(app.config.get("KILLKRILL_GRPC_URL", "")),
            client_id=str(app.config.get("KILLKRILL_CLIENT_ID", "")),
            client_secret=str(app.config.get("KILLKRILL_CLIENT_SECRET", "")),
            enabled=bool(app.config.get("KILLKRILL_ENABLED", False)),
        )

    # Setup structured request logging middleware
    setup_request_logging(app)

    # Register blueprints
    from .openapi import register_openapi_routes

    from .auth import auth_bp
    from .audit import audit_bp
    from .dashboard_api import dashboard_bp
    from .discovery import discovery_bp
    from .hello import hello_bp
    from .license_api import license_bp
    from .mfa import mfa_bp
    from .oauth import oauth_bp
    from .products import products_bp
    from .operations_api import operations_bp
    from .proxy import proxy_bp
    from .teams import teams_bp
    from .tenants import tenants_bp
    from .users import users_bp

    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    app.register_blueprint(users_bp, url_prefix="/api/v1/users")
    app.register_blueprint(hello_bp, url_prefix="/api/v1")
    app.register_blueprint(license_bp, url_prefix="/api/v1/license")
    app.register_blueprint(oauth_bp, url_prefix="/api/v1")
    app.register_blueprint(teams_bp, url_prefix="/api/v1/teams")
    app.register_blueprint(mfa_bp, url_prefix="/api/v1/mfa")
    app.register_blueprint(tenants_bp, url_prefix="/api/v1/tenants")
    app.register_blueprint(products_bp, url_prefix="/api/v1/products")
    # Long-running operation polling shares the products prefix: an
    # operation is always addressed through the connection that owns it.
    app.register_blueprint(operations_bp, url_prefix="/api/v1/products")
    # No url_prefix: proxy_bp's rule already carries its full path
    # (/api/v1/products/<id>/proxy/<path>). Registering it under a prefix
    # nested it at /api/v1/proxy/api/v1/products/... — every allowlist rule
    # was intact and unreachable, which is a deny-by-default proxy failing
    # in the safe direction and therefore silent.
    app.register_blueprint(proxy_bp)
    app.register_blueprint(discovery_bp, url_prefix="/api/v1/discovery")
    app.register_blueprint(dashboard_bp, url_prefix="/api/v1/dashboard")
    app.register_blueprint(audit_bp, url_prefix="/api/v1/audit")

    # OpenAPI: public (login only) + authenticated (full). Registered
    # after the blueprints so the generated document sees every route.
    register_openapi_routes(app)

    # Health check endpoint (async)
    @app.route("/healthz")
    async def health_check() -> tuple[dict[str, Any], int]:
        """Health check endpoint.

        Tests database connectivity by attempting a simple query.
        """
        try:
            db = get_db()
            # Simple connectivity probe: read at most one user row.
            _ = await db(db.users.id > 0).select(limitby=(0, 1))
            return {"status": "healthy", "database": "connected"}, 200
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}, 503

    # Readiness check endpoint (async)
    @app.route("/readyz")
    async def readiness_check() -> tuple[dict[str, str], int]:
        """Readiness check endpoint."""
        return {"status": "ready"}, 200

    return app
