"""Quart Backend Application Factory (async-native)."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

from penguin_aaa.authn.oidc_provider import OIDCProvider, OIDCProviderConfig
from penguin_aaa.crypto.keystore import FileKeyStore, KeyStore, MemoryKeyStore
from penguin_dal.quart_ext import get_db, init_dal
from quart import Quart
from quart_cors import cors
from quart_schema import HttpSecurityScheme, Info, QuartSchema

from . import devmode
from .adapter_errors import UPSTREAM_RESPONSE_HEADER
from .background import get_background_manager
from .config import (
    MIN_SECRET_KEY_LENGTH,
    PUBLISHED_INSECURE_SECRET_KEY_VALUES,
    Config,
)
from .killkrill import killkrill_manager
from .license import license_manager
from .middleware import setup_request_logging

log = logging.getLogger(__name__)


def _require_configured_secret_key(app: Quart) -> None:
    """Refuse to start with an unconfigured SECRET_KEY outside TESTING.

    Quart signs the session cookie with SECRET_KEY (itsdangerous), and
    app/oauth.py's ``oauth_state`` CSRF check lives entirely inside that
    signed session — a cookie signed with a KNOWN key is exactly as
    forgeable as an unsigned one, defeating the CSRF check it exists to
    enforce and enabling OAuth account-linking CSRF.

    Round-1 review (C1): the original check was a single ``!=`` against
    ONE literal, and every one of the below evaded it — the app started,
    signing ACTIVE, with no error, no log, nothing:

    * ``"dev-secret-key-change-in-production "`` — one trailing space,
      exactly what a ``.env`` line or a YAML block scalar produces
      routinely. Fixed by ``.strip()``-normalising before comparing.
    * ``"change-me-in-production"`` — docker-compose.yml's OWN former
      fallback for this same variable. This fix's docker-compose.yml edit
      (removing that fallback) would otherwise have stranded every
      developer who already had it in their ``.env``/shell on a still-
      published key while this guard reported green — the commit
      creating the exact gap it exists to close. Fixed by denylisting
      BOTH published values (``PUBLISHED_INSECURE_SECRET_KEY_VALUES``),
      not just this file's own default.
    * ``""`` and ``"   "`` — empty or whitespace-only. Neither equals the
      denylisted literal, so the old check passed them straight through;
      Quart's session machinery then either silently disables sessions
      (empty) or signs with a key indistinguishable from no key at all.
      Fixed by rejecting anything falsy after normalising, before even
      reaching the denylist comparison.

    ``MIN_SECRET_KEY_LENGTH`` additionally rejects trivially short values
    that were never published anywhere ("test", "admin"). It is a floor,
    NOT a strength or entropy guarantee: a one-character variant of a
    long published string (e.g. ``"change-me-in-productioN"``) still
    clears it and is not caught by anything here. Real entropy/similarity
    detection was judged out of scope for this fix — it risks false
    positives against genuinely-random real secrets, and the denylist
    plus length floor close every evasion actually demonstrated, not
    every value that is theoretically guessable.

    Same reasoning as app/encryption.py's ``_get_fernet`` check for
    ENCRYPTION_KEY, and the same TESTING-only carve-out: an unset
    security-critical secret must stop the process, not silently sign
    every cookie with a value an attacker can read on GitHub. Checked
    eagerly here (app startup) rather than lazily on first session access
    the way encryption.py checks ENCRYPTION_KEY on first encrypt/decrypt
    call — every request touches the session, so there is no narrower
    "first real use" moment to defer to.
    """
    if app.config.get("TESTING"):
        return

    raw = app.config["SECRET_KEY"]
    normalized = raw.strip() if isinstance(raw, str) else ""

    if (
        normalized
        and normalized not in PUBLISHED_INSECURE_SECRET_KEY_VALUES
        and len(normalized) >= MIN_SECRET_KEY_LENGTH
    ):
        return

    raise RuntimeError(
        "SECRET_KEY is not configured with a real secret (unset, empty, "
        "whitespace-only, a known published placeholder, or shorter than "
        f"{MIN_SECRET_KEY_LENGTH} characters after trimming whitespace). "
        "Quart signs session cookies -- including the OAuth CSRF state "
        "app/oauth.py's callback relies on -- with this key, so a known "
        "or trivial key makes that state forgeable. Set SECRET_KEY to a "
        "real, unpredictable secret (see docs/DEVELOPMENT.md) before "
        "starting outside TESTING."
    )


def _build_oidc_provider(app: Quart) -> OIDCProvider:
    """Build the penguin-aaa OIDC provider backing this app's tokens.

    Four outcomes, chosen deliberately rather than guessed:

    * ``JWT_KEYSTORE_PATH`` set -> ``FileKeyStore``. Every process pointed
      at the SAME path loads the SAME signing key, so a token minted by
      one verifies on every other. See docs/DEVELOPMENT.md "JWT Signing
      Keystore" for how that file/mount is expected to get there. The
      loaded keystore is probed once here (``get_signing_key()``) so a
      keystore file that parses but holds zero keys — e.g. a hand-
      authored Secret written as ``{"keys": []}``, which
      ``FileKeyStore._load`` (keystore.py:196-204) accepts without
      complaint — fails loudly at BOOT with a clear message, not with a
      bare ``IndexError`` at the first token mint (round-1 M6).
    * ``JWT_KEYSTORE_PATH`` unset AND either ``DEPLOYMENT_REPLICAS`` or
      ``HYPERCORN_WORKERS`` was never explicitly declared (only
      defaulted) -> refuse to start. Round-1 I1: nothing in this
      repository sets ``DEPLOYMENT_REPLICAS`` today (the Helm chart is a
      stub, neither compose file declares it), so a check that only
      fires on ``> 1`` is INERT in every deployment that exists — it
      fails OPEN. Requiring an explicit declaration on both axes (compose
      and ``TestingConfig`` declare ``1``; see ``config.py``) means an
      operator who never heard of either variable is refused rather than
      silently assumed single-process, which is the actual asymmetry with
      ``_require_configured_secret_key`` above: that one fails CLOSED on
      unset, this one used to fail open.
    * ``JWT_KEYSTORE_PATH`` unset AND declared, but
      ``DEPLOYMENT_REPLICAS * HYPERCORN_WORKERS > 1`` -> refuse to start.
      Round-1 I3: the failure domain that matters is PROCESSES, not
      Kubernetes replicas — ``hypercorn --workers N`` calls
      ``create_app()`` once per OS process, each building its own
      ``MemoryKeyStore``, which is the identical cross-verification
      failure on a SINGLE pod with ``DEPLOYMENT_REPLICAS=1``. Falling
      back to a private in-process key here would mean every process
      signs with a key none of the others can verify — intermittent 401s
      that track load-balancer/worker routing, not an outage, and exactly
      the kind of bug that vanishes the moment anyone tests against a
      single process. A loud failure at boot beats a silent wrong answer
      at request time. (``services/portal-api/Dockerfile`` pins
      ``--workers`` via this same ``HYPERCORN_WORKERS`` variable, so the
      process count hypercorn actually launches and the count this check
      reads can never drift apart under that Dockerfile's CMD — a
      DIFFERENT entrypoint that hardcodes ``--workers`` some other way is
      not covered, which is why this is a declared count, not a detected
      one.)
    * ``JWT_KEYSTORE_PATH`` unset, both declared, exactly one effective
      process -> ``MemoryKeyStore``, exactly as before -- but the choice
      is now ANNOUNCED (WARN, naming the consequence) rather than merely
      documented in a docstring nothing enforced. Same reasoning
      general.md gives for the --dev notice: an operator who did not
      configure the deployment still needs to know what mode it is
      running in.
    """
    algorithm: str = app.config["JWT_ALGORITHM"]
    keystore_path: str = app.config["JWT_KEYSTORE_PATH"]
    replicas: int = app.config["DEPLOYMENT_REPLICAS"]
    replicas_declared: bool = app.config["DEPLOYMENT_REPLICAS_DECLARED"]
    workers: int = app.config["HYPERCORN_WORKERS"]
    workers_declared: bool = app.config["HYPERCORN_WORKERS_DECLARED"]
    effective_processes = replicas * workers
    keystore: KeyStore

    if keystore_path:
        keystore = FileKeyStore(Path(keystore_path), algorithm=algorithm)
        try:
            keystore.get_signing_key()
        except IndexError:
            raise RuntimeError(
                f"JWT_KEYSTORE_PATH={keystore_path!r} loaded with zero "
                "signing keys. penguin_aaa.crypto.keystore.FileKeyStore."
                '_load reads an existing file\'s "keys" list as-is -- a '
                'hand-authored Secret written as {"keys": []} loads '
                "successfully here and only fails later, at the first "
                "token mint, with a bare IndexError from "
                "get_signing_key(). Refusing to start now instead: "
                "re-provision the keystore with at least one key (see "
                "docs/DEVELOPMENT.md: 'JWT Signing Keystore')."
            ) from None
        log.info(
            "jwt_keystore_selected kind=file replicas=%d workers=%d path=%s",
            replicas,
            workers,
            keystore_path,
        )
    elif not (replicas_declared and workers_declared):
        raise RuntimeError(
            "JWT_KEYSTORE_PATH is unset AND at least one of "
            "DEPLOYMENT_REPLICAS/HYPERCORN_WORKERS was never explicitly "
            "declared (only defaulted). Refusing to assume this is a "
            "single process: an undeclared deployment topology is "
            "exactly how a multi-replica or multi-worker rollout "
            "silently inherits the per-process MemoryKeyStore bug this "
            "guard exists to catch. Declare BOTH DEPLOYMENT_REPLICAS and "
            "HYPERCORN_WORKERS explicitly (1 for a genuinely "
            "single-process deployment), or set JWT_KEYSTORE_PATH."
        )
    elif effective_processes > 1:
        raise RuntimeError(
            f"DEPLOYMENT_REPLICAS={replicas} x HYPERCORN_WORKERS={workers} "
            f"= {effective_processes} processes but JWT_KEYSTORE_PATH is "
            "unset. Refusing to start rather than mint tokens with a "
            "private per-process key: every OTHER process would reject "
            "them as an invalid signature, which surfaces as intermittent "
            "401s that track load-balancer/worker routing rather than as "
            "an outage. Set JWT_KEYSTORE_PATH to a keystore shared by "
            "every process (see docs/DEVELOPMENT.md: 'JWT Signing "
            "Keystore'), or set both DEPLOYMENT_REPLICAS=1 and "
            "HYPERCORN_WORKERS=1 if this is genuinely a single-process "
            "deployment."
        )
    else:
        keystore = MemoryKeyStore(algorithm=algorithm)
        log.warning(
            "jwt_keystore_is_per_process_only "
            "reason=JWT_KEYSTORE_PATH_not_configured "
            "consequence='signing keys live only in this process's memory: "
            "they are lost on restart, and a token minted by a DIFFERENT "
            "process (another replica, another hypercorn worker, or an "
            "earlier run) is rejected as an invalid signature, not as "
            "expired' "
            "fix='set JWT_KEYSTORE_PATH (docs/DEVELOPMENT.md: JWT Signing "
            "Keystore) before running more than one process of this "
            "service'"
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

    # Secure by default: refuse to sign session cookies with the public
    # placeholder SECRET_KEY outside TESTING. Checked immediately after
    # config load, before anything (session, CORS, blueprints) could rely
    # on it. See _require_configured_secret_key's docstring.
    _require_configured_secret_key(app)

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
        security_schemes={"bearerAuth": HttpSecurityScheme(scheme="bearer", bearer_format="JWT")},
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
        # Without this, a browser's fetch/XHR strips any response header not
        # explicitly exposed — including UPSTREAM_RESPONSE_HEADER, the
        # provenance marker services/webui/src/client/lib/mutationError.ts
        # trusts to decide whether a body is safe to show verbatim. Today
        # the webui always reaches this API same-origin through the Express
        # BFF, where that stripping does not apply — but the CORS allowlist
        # above exists AT ALL because cross-origin access was once intended,
        # and if the client is ever pointed at this origin directly, an
        # unexposed header would make every upstream-forwarded body read as
        # "trusted" with no code change on either side to notice. The safe
        # behaviour should not depend on a deployment topology nobody
        # re-checks.
        expose_headers=[UPSTREAM_RESPONSE_HEADER],
    )

    # Initialize the OIDC token provider (penguin-aaa). Every token this app
    # issues or verifies goes through it, so failing to register it leaves
    # auth_required returning 500 on every protected route.
    app.extensions["oidc_provider"] = _build_oidc_provider(app)

    # Registered BEFORE init_dal() below on purpose. Quart runs
    # after_serving hooks in REGISTRATION order (app.after_serving_funcs is
    # a plain list, appended to and iterated in order -- verified against
    # quart/app.py, not assumed), and init_dal() registers its own
    # `_shutdown_dal` (closes the AsyncDB pool) as an after_serving hook
    # internally. Registering this one first means it also RUNS first at
    # shutdown: every background task -- including a health-poll sweep that
    # may be mid-flight -- is cancelled and awaited before the pool it reads
    # from closes underneath it. Registered the other way round once, and a
    # graceful shutdown could close the pool while a sweep was still
    # running: poll_forever has no way to tell "the DB closed because we're
    # shutting down" from "the DB failed", so it read every such shutdown as
    # a crash and logged a spurious health_poll_loop_crashed plus an
    # unnecessary 5s backoff sleep before the process could exit.
    @app.after_serving
    async def _stop_background_tasks() -> None:
        """Cancel and await every background task, before the DAL closes."""
        await get_background_manager().stop()

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

    # Record whether --dev was passed. Deliberately only RECORDS the
    # request: activation additionally requires a PenguinTech domain and
    # at most one user, and is re-evaluated per request rather than
    # latched here (general.md calls a boot-time latch a licensing hole).
    # Both calls are synchronous and immediate (not before_serving hooks),
    # so they carry no ordering dependency on init_dal or the background
    # task hooks registered below.
    devmode.request_from_argv()
    devmode.announce_at_startup()

    # Start background tasks (license keepalive + product health poller).
    #
    # BackgroundTaskManager.start() was previously called from nowhere in
    # create_app -- the license keepalive loop it has always owned had
    # therefore never run in any deployment. Registered AFTER init_dal()
    # (above) on purpose, mirroring _stop_background_tasks' ordering
    # concern from the other end: init_dal()'s `_reflect_tables` before_
    # serving hook must run BEFORE this one, so the health poller's first
    # sweep never races table reflection. _stop_background_tasks (above,
    # registered before init_dal) cancels both loops cleanly on shutdown.
    @app.before_serving
    async def _start_background_tasks() -> None:
        """Start the license keepalive and product health poller loops."""
        from .health_cache import log_startup_state

        # Unmistakable at startup whether the health cache is shared
        # (CACHE_HOST set) or per-process-only -- see health_cache.py's
        # log_startup_state docstring (Task 6 fix wave 1, I4).
        log_startup_state(app.config)

        get_background_manager().start()

        # Metrics get their own :9090 listener (app/health_poller.py) --
        # never in the test suite, which creates a fresh app per test and
        # would otherwise repeatedly (and pointlessly) attempt a real
        # socket bind.
        if not app.config.get("TESTING"):
            from .health_poller import start_metrics_server

            start_metrics_server(int(app.config.get("HEALTH_METRICS_PORT", 9090)))

    # Setup structured request logging middleware
    setup_request_logging(app)

    # Register blueprints
    from .audit import audit_bp
    from .auth import auth_bp
    from .console_manifests import console_manifests_bp
    from .dashboard_api import dashboard_bp
    from .discovery import discovery_bp
    from .features_api import features_bp
    from .health_api import health_api_bp
    from .hello import hello_bp
    from .license_api import license_bp
    from .mfa import mfa_bp
    from .oauth import oauth_bp
    from .openapi import register_openapi_routes
    from .operations_api import operations_bp
    from .products import products_bp
    from .proxy import proxy_bp
    from .resources_api import resources_bp
    from .teams import teams_bp
    from .tenants import tenants_bp
    from .users import users_bp

    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    app.register_blueprint(users_bp, url_prefix="/api/v1/users")
    app.register_blueprint(hello_bp, url_prefix="/api/v1")
    app.register_blueprint(features_bp, url_prefix="/api/v1")
    app.register_blueprint(license_bp, url_prefix="/api/v1/license")
    app.register_blueprint(oauth_bp, url_prefix="/api/v1")
    app.register_blueprint(teams_bp, url_prefix="/api/v1/teams")
    app.register_blueprint(mfa_bp, url_prefix="/api/v1/mfa")
    app.register_blueprint(tenants_bp, url_prefix="/api/v1/tenants")
    app.register_blueprint(products_bp, url_prefix="/api/v1/products")
    # Cached, tenant-scoped health rollup -- shares the products prefix for
    # the same reason operations/resources do (see below), and is its own
    # blueprint/module (app/health_api.py) rather than another route in
    # products.py, which is already close to this repo's largest module.
    app.register_blueprint(health_api_bp, url_prefix="/api/v1/products")
    # Long-running operation polling shares the products prefix: an
    # operation is always addressed through the connection that owns it.
    app.register_blueprint(operations_bp, url_prefix="/api/v1/products")
    # Typed resource writes share the same prefix for the same reason: a
    # resource is only addressable through the connection that owns it.
    # Reads are NOT here — those go through the proxy allowlist.
    app.register_blueprint(resources_bp, url_prefix="/api/v1/products")
    # No url_prefix: proxy_bp's rule already carries its full path
    # (/api/v1/products/<id>/proxy/<path>). Registering it under a prefix
    # nested it at /api/v1/proxy/api/v1/products/... — every allowlist rule
    # was intact and unreachable, which is a deny-by-default proxy failing
    # in the safe direction and therefore silent.
    app.register_blueprint(proxy_bp)
    app.register_blueprint(discovery_bp, url_prefix="/api/v1/discovery")
    app.register_blueprint(dashboard_bp, url_prefix="/api/v1/dashboard")
    app.register_blueprint(audit_bp, url_prefix="/api/v1/audit")
    app.register_blueprint(console_manifests_bp, url_prefix="/api/v1/console")

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
