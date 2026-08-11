"""Pytest configuration and shared fixtures for API tests."""

import atexit
import os
import shutil
import sys
import tempfile
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import jwt
import pytest_asyncio
from quart import Quart

# Ensure the flask backend app can be imported
backend_path = os.path.join(os.path.dirname(__file__), "../services/portal-api")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

# Set TESTING mode early
os.environ["TESTING"] = "true"

# Give this pytest process a private, unique SQLite path for TestingConfig
# (see app.config.TestingConfig) before any test module is collected. Some
# test modules import `app.config` at module scope, which runs the
# TestingConfig class body — and thus resolves TEST_DB_PATH — during
# collection, before any fixture would get a chance to run. conftest.py is
# always imported ahead of test module collection, so setting the env var
# here (rather than in a fixture) guarantees it wins the class body's
# `os.environ.get("TEST_DB_PATH") or ...` fallback every time.
#
# tempfile.mkdtemp() (not a bare literal) keeps this collision-free across
# concurrent/parallel pytest invocations; registering cleanup at process
# exit avoids leaving stale directories behind in /tmp between runs.
_test_db_dir = tempfile.mkdtemp(prefix="penguincloud-pytest-")
os.environ.setdefault("TEST_DB_PATH", os.path.join(_test_db_dir, "test.db"))
atexit.register(shutil.rmtree, _test_db_dir, ignore_errors=True)

# Enable pytest-asyncio
pytest_plugins = ("pytest_asyncio",)


@pytest_asyncio.fixture
async def app() -> AsyncGenerator[Quart]:
    """Create and configure a test Quart app (async)."""
    from app import create_app
    from app.config import TestingConfig
    from app.models_sqlalchemy import Base
    from penguin_dal.quart_ext import get_db
    from sqlalchemy import create_engine

    test_app = create_app(config_class=TestingConfig)

    # Create all tables from SQLAlchemy models for testing
    # (real production uses Alembic migrations)
    db_path = TestingConfig.DB_NAME
    db_uri = f"sqlite:///{db_path}"
    engine = create_engine(db_uri)
    Base.metadata.create_all(engine)
    engine.dispose()

    # Reflect tables into penguin-dal's metadata
    # (normally happens in @app.before_serving async hook, but tests don't trigger it)
    async with test_app.app_context():
        db = get_db()
        await db.reflect()

    yield test_app

    # Cleanup: penguin-dal manages connections via app.extensions, no explicit
    # close needed in test fixtures (the after_serving hook handles shutdown)


@pytest_asyncio.fixture(autouse=True)
def _clear_tenancy_cache() -> Any:
    """Empty the resolver's in-process subtree cache around every test.

    The cache is a module-level dict with a 60s TTL, so without this a
    subtree set memoised by one test stays live for the rest of the pytest
    process. Tests would then pass or fail depending on execution order —
    and, worse, a cache-invalidation test could pass purely because no
    earlier test had populated the key it expects to see cleared.
    """
    from app.tenancy import clear_local_cache

    clear_local_cache()
    yield
    clear_local_cache()


@pytest_asyncio.fixture(autouse=True)
def _reset_killkrill_manager() -> Any:
    """Disable the process-wide KillKrillManager singleton after every test.

    Discovered while adding tests/api/test_background_tasks.py, the first
    tests in this suite to ever drive the app's real ASGI lifespan
    (app.test_app()). Doing so runs create_app's `_init_killkrill`
    before_serving hook, which -- because KILLKRILL_ENABLED defaults to
    "true" and TestingConfig does not override it -- flips the SINGLETON
    `app.killkrill.killkrill_manager` to enabled=True for the rest of the
    pytest PROCESS. Every subsequent test's HTTP request then also calls
    killkrill_manager.log() via middleware.setup_request_logging's
    after_request hook, appending to an in-memory queue nothing ever
    flushes (app.killkrill.KillKrillManager._flush_queues is itself dead
    code -- not called from anywhere) and emitting one
    `datetime.utcnow()` DeprecationWarning per request. Without this reset
    the effect is silent everywhere except the warnings count, but it is a
    genuine test-isolation gap: which tests run before a lifespan-driving
    one changes their behaviour.
    """
    yield
    from app.killkrill import killkrill_manager

    killkrill_manager.enabled = False
    killkrill_manager.client = None
    killkrill_manager._log_queue.clear()
    killkrill_manager._metric_queue.clear()


@pytest_asyncio.fixture(autouse=True)
def _clear_health_cache() -> Any:
    """Empty the health poller's module-level cache state around every test.

    Same reasoning as _clear_tenancy_cache above: app.health_cache keeps a
    per-process in-memory fallback dict plus a memoised Valkey client, both
    module-level. Without this, a connection_id reused across tests (SQLite
    autoincrement restarts per test DB, but the shared file-based DB means
    ids are NOT guaranteed test-local — see conftest's TEST_DB_PATH comment)
    could read another test's cached health, and a test that monkeypatches
    CACHE_HOST to exercise the Valkey path would leak a stale client into
    whatever runs next.
    """
    from app.health_cache import clear_local_cache, reset_cache_client_for_tests

    clear_local_cache()
    reset_cache_client_for_tests()
    yield
    clear_local_cache()
    reset_cache_client_for_tests()


@pytest_asyncio.fixture
async def app_context(app: Quart) -> AsyncGenerator[None]:
    """Provide active app context for tests calling model functions directly."""
    async with app.app_context():
        yield


@pytest_asyncio.fixture
async def client(app: Quart) -> Any:
    """Create async test client for Quart app."""
    return app.test_client()


@pytest_asyncio.fixture
async def user_id(client: Any) -> int:
    """Register and login a test user, return user ID (async)."""
    # Unique email — see auth_headers below; the shared file-based sqlite
    # DB persists across the whole pytest process (TestingConfig.DB_NAME is
    # resolved once), so a fixed literal risks colliding with another
    # test's registration in the same session.
    unique_email = f"testuser{uuid.uuid4().hex[:8]}@example.com"

    # Register
    register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "testpass123",
            "full_name": "Test User",
        },
    )
    assert register_response.status_code in [
        200,
        201,
    ], f"Failed to register: {await register_response.get_json()}"

    # Login to get token
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": "testpass123"},
    )
    assert login_response.status_code == 200, f"Failed to login: {await login_response.get_json()}"

    token = (await login_response.get_json())["access_token"]

    # Access tokens are now RS256, signed by penguin-aaa's keystore (the old
    # hand-rolled HS256/JWT_SECRET_KEY scheme is gone). This fixture only
    # needs the subject, and the token was just minted by the app under
    # test, so decode without signature verification rather than plumbing
    # the JWKS in here — auth_required is what actually verifies signatures,
    # and tests/api/test_auth.py covers that path.
    payload = jwt.decode(token, options={"verify_signature": False})
    return int(payload["sub"])


@pytest_asyncio.fixture
async def admin_headers(client: Any, app: Quart) -> dict[str, str]:
    """Create a genuine admin-role authenticated user.

    Registration always defaults to role="viewer" (see auth.py:register) —
    there is no self-service way to become admin. Elevate the role via the
    DB layer inside an app context, then log in again so the fresh JWT's
    `roles` claim (baked in at token issuance) reflects it.

    Lived in test_audit.py/test_license.py as duplicated local fixtures
    before the Quart migration; shared here so both suites use one
    async-ported definition.
    """
    unique_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "adminpass123",
            "full_name": "Admin User",
        },
    )
    assert register_response.status_code in [
        200,
        201,
    ], f"Failed to register: {await register_response.get_json()}"
    new_user_id = (await register_response.get_json())["user"]["id"]

    async with app.app_context():
        from app.models import update_user

        await update_user(new_user_id, role="admin")

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": "adminpass123"},
    )
    assert response.status_code == 200, f"Failed to login: {await response.get_json()}"

    token = (await response.get_json())["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def tenant_id(client: Any, admin_headers: dict[str, str]) -> int:
    """Create a tenant owned by the admin_headers user; return its id.

    create_tenant() (unlike create_team()) adds the creator as a
    tenant_members row with role="owner", so this gives audit/license tests
    a tenant the admin user genuinely has owner role on — which is what the
    tenant-scoped endpoints require.
    """
    response = await client.post(
        "/api/v1/tenants",
        headers=admin_headers,
        json={
            "name": "Audit Test Tenant",
            "slug": f"audit-tenant-{uuid.uuid4().hex[:8]}",
            "plan": "free",
        },
    )
    assert response.status_code == 201, f"Failed to create tenant: {await response.get_json()}"
    return int((await response.get_json())["id"])


@pytest_asyncio.fixture
async def auth_headers(client: Any) -> dict[str, str]:
    """Create authenticated headers for API requests (async)."""
    # Use unique email to avoid conflicts
    unique_email = f"test{uuid.uuid4().hex[:8]}@example.com"

    # Register
    register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "testpass123",
            "full_name": "Test User",
        },
    )

    assert register_response.status_code in [
        200,
        201,
    ], f"Failed to register: {await register_response.get_json()}"

    # Login
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": "testpass123"},
    )

    assert login_response.status_code == 200, f"Failed to login: {await login_response.get_json()}"
    token = (await login_response.get_json())["access_token"]
    return {"Authorization": f"Bearer {token}"}
