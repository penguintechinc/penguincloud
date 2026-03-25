"""Flask Backend Application Factory."""

from flask import Flask
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from prometheus_client import make_wsgi_app
from werkzeug.middleware.dispatcher import DispatcherMiddleware

from .background import get_background_manager
from .config import Config
from .killkrill import killkrill_manager
from .license import license_manager
from .middleware import setup_request_logging
from .models import get_db, init_db

# Global rate limiter instance
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per minute"],
    storage_uri="memory://",
)


def create_app(config_class: type = Config) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Set session configuration for OAuth state management
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    # Initialize rate limiter
    limiter.init_app(app)

    # Initialize CORS
    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": app.config.get("CORS_ORIGINS", "*"),
                "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                "allow_headers": ["Content-Type", "Authorization"],
            }
        },
    )

    # Initialize database
    with app.app_context():
        init_db(app)

    # Initialize license
    with app.app_context():
        if not license_manager.validate():
            if app.config.get("RELEASE_MODE"):
                raise RuntimeError("License validation failed in RELEASE_MODE")
        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"License Status: {license_manager.get_status()}")

    # Initialize KillKrill
    killkrill_manager.setup(
        api_url=app.config.get("KILLKRILL_API_URL"),
        grpc_url=app.config.get("KILLKRILL_GRPC_URL"),
        client_id=app.config.get("KILLKRILL_CLIENT_ID"),
        client_secret=app.config.get("KILLKRILL_CLIENT_SECRET"),
        enabled=app.config.get("KILLKRILL_ENABLED"),
    )

    # Setup structured request logging middleware
    setup_request_logging(app)

    # Register blueprints
    from .auth import auth_bp
    from .hello import hello_bp
    from .license_api import license_bp
    from .mfa import mfa_bp
    from .oauth import oauth_bp
    from .teams import teams_bp
    from .users import users_bp

    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    app.register_blueprint(users_bp, url_prefix="/api/v1/users")
    app.register_blueprint(hello_bp, url_prefix="/api/v1")
    app.register_blueprint(license_bp, url_prefix="/api/v1/license")
    app.register_blueprint(oauth_bp, url_prefix="/api/v1")
    app.register_blueprint(teams_bp, url_prefix="/api/v1/teams")
    app.register_blueprint(mfa_bp, url_prefix="/api/v1/mfa")

    # PenguinCloud blueprints
    from .audit import audit_bp
    from .dashboard_api import dashboard_bp
    from .discovery import discovery_bp
    from .products import products_bp
    from .proxy import proxy_bp
    from .tenants import tenants_bp

    app.register_blueprint(tenants_bp, url_prefix="/api/v1/tenants")
    app.register_blueprint(products_bp, url_prefix="/api/v1/products")
    app.register_blueprint(proxy_bp, url_prefix="/api/v1/proxy")
    app.register_blueprint(discovery_bp, url_prefix="/api/v1/discovery")
    app.register_blueprint(dashboard_bp, url_prefix="/api/v1/dashboard")
    app.register_blueprint(audit_bp, url_prefix="/api/v1/audit")

    # Health check endpoint
    @app.route("/healthz")
    def health_check():
        """Health check endpoint."""
        try:
            db = get_db()
            db.executesql("SELECT 1")
            return {"status": "healthy", "database": "connected"}, 200
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}, 503

    # Readiness check endpoint
    @app.route("/readyz")
    def readiness_check():
        """Readiness check endpoint."""
        return {"status": "ready"}, 200

    # Add Prometheus metrics endpoint
    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {"/metrics": make_wsgi_app()})

    # Start background tasks
    with app.app_context():
        bg_manager = get_background_manager()
        bg_manager.start()

    return app
