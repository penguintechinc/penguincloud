"""Pytest configuration and shared fixtures for API tests."""

from typing import Any, Generator
import os
import sys
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


@pytest.fixture
def app() -> Generator[Flask, None, None]:
    """Create and configure a test Flask app."""
    from app.config import TestingConfig
    from app import create_app

    test_app = create_app(config_class=TestingConfig)
    yield test_app


@pytest.fixture
def client(app: Flask) -> Any:
    """Create a test client."""
    return app.test_client()


@pytest.fixture
def user_id(client: Any) -> int:
    """Register and login a test user, return user ID."""
    from app.config import TestingConfig

    # Register
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "testuser@example.com",
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
        json={"email": "testuser@example.com", "password": "testpass123"},
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
