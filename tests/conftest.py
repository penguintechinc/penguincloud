"""Pytest configuration and shared fixtures for API tests."""

from typing import Any, Generator
import atexit
import os
import shutil
import sys
import tempfile
import uuid
import jwt
import pytest
from flask import Flask

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


@pytest.fixture
def app() -> Generator[Flask, None, None]:
    """Create and configure a test Flask app."""
    from app.config import TestingConfig
    from app import create_app

    test_app = create_app(config_class=TestingConfig)
    yield test_app

    # Every test gets a fresh create_app() -> init_db() call, which opens a
    # brand new PyDAL connection against the SAME shared file-based sqlite
    # DB (TestingConfig.DB_NAME is resolved once per pytest process). Without
    # an explicit close here, each test's connection is left open and relies
    # on GC timing to release its SQLite lock — under a full-file run this
    # reliably produces `sqlite3.OperationalError: database is locked` on a
    # later test's write. Close deterministically at teardown instead.
    db = test_app.config.get("db")
    if db is not None:
        db.close()


@pytest.fixture
def client(app: Flask) -> Any:
    """Create a test client."""
    return app.test_client()


@pytest.fixture
def user_id(client: Any) -> int:
    """Register and login a test user, return user ID."""
    from app.config import TestingConfig

    # Unique email — see auth_headers below; the shared file-based sqlite
    # DB persists across the whole pytest process (TestingConfig.DB_NAME is
    # resolved once), so a fixed literal risks colliding with another
    # test's registration in the same session.
    unique_email = f"testuser{uuid.uuid4().hex[:8]}@example.com"

    # Register
    register_response = client.post(
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
    ], f"Failed to register: {register_response.get_json()}"

    # Login to get token
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": "testpass123"},
    )
    assert (
        login_response.status_code == 200
    ), f"Failed to login: {login_response.get_json()}"

    token = login_response.get_json()["access_token"]

    # Decode token to get user_id
    payload = jwt.decode(token, TestingConfig.JWT_SECRET_KEY, algorithms=["HS256"])
    return int(payload["sub"])


@pytest.fixture
def auth_headers(client: Any) -> dict[str, str]:
    """Create authenticated headers for API requests."""
    # Use unique email to avoid conflicts
    unique_email = f"test{uuid.uuid4().hex[:8]}@example.com"

    # Register
    register_response = client.post(
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
    ], f"Failed to register: {register_response.get_json()}"

    # Login
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": "testpass123"},
    )

    assert (
        login_response.status_code == 200
    ), f"Failed to login: {login_response.get_json()}"
    token = login_response.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
