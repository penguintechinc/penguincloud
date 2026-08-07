"""Pytest configuration and shared fixtures for API tests."""

from typing import Any, AsyncGenerator
import atexit
import os
import shutil
import sys
import tempfile
import uuid
import jwt
import pytest_asyncio
from quart import Quart

# Ensure the flask backend app can be imported
backend_path = os.path.join(os.path.dirname(__file__), "../services/flask-backend")
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
async def app() -> AsyncGenerator[Quart, None]:
    """Create and configure a test Quart app (async)."""
    from app.config import TestingConfig
    from app import create_app
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


@pytest_asyncio.fixture
async def client(app: Quart) -> Any:
    """Create async test client for Quart app."""
    return app.test_client()


@pytest_asyncio.fixture
async def user_id(client: Any) -> int:
    """Register and login a test user, return user ID (async)."""
    from app.config import TestingConfig

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
    assert (
        login_response.status_code == 200
    ), f"Failed to login: {await login_response.get_json()}"

    token = (await login_response.get_json())["access_token"]

    # Decode token to get user_id
    payload = jwt.decode(
        token, TestingConfig.JWT_SECRET_KEY, algorithms=["HS256"]
    )
    return int(payload["sub"])


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

    assert (
        login_response.status_code == 200
    ), f"Failed to login: {await login_response.get_json()}"
    token = (await login_response.get_json())["access_token"]
    return {"Authorization": f"Bearer {token}"}
