"""Pytest configuration and shared fixtures for API tests."""

from typing import Any, AsyncGenerator
import atexit
import os
import shutil
import sys
import tempfile
import uuid
import jwt
import pytest
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
        # Freeze the quota baseline HERE, before any other fixture has
        # created a tenant, team or admin. Priming it at first use instead
        # would silently exclude whatever the test's own fixtures built
        # during setup, which is precisely the structure most quota tests
        # are about. See _quota_counts_are_per_test.
        await _prime_quota_baselines()

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


@pytest_asyncio.fixture
async def app_context(app: Quart) -> AsyncGenerator[None, None]:
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
    assert (
        login_response.status_code == 200
    ), f"Failed to login: {await login_response.get_json()}"

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
    assert (
        response.status_code == 200
    ), f"Failed to login: {await response.get_json()}"

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
    assert (
        response.status_code == 201
    ), f"Failed to create tenant: {await response.get_json()}"
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

    assert (
        login_response.status_code == 200
    ), f"Failed to login: {await login_response.get_json()}"
    token = (await login_response.get_json())["access_token"]
    return {"Authorization": f"Bearer {token}"}


#: Deployment-wide counters whose rows survive from one test to the next
#: because the SQLite file does.
_ACCUMULATING_COUNTERS = (
    "count_tenants",
    "count_teams",
    "count_global_admins",
    "count_tenant_admins",
    "count_objects",
)


async def _prime_quota_baselines() -> None:
    """Capture the pre-test value of every accumulating counter."""
    from app import quotas

    for counter in _ACCUMULATING_COUNTERS:
        await getattr(quotas, counter)()


@pytest.fixture(autouse=True)
def _quota_counts_are_per_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Measure every quota dimension from where THIS test started.

    The quota walls are LIVE for the whole suite — the licensed limits are
    the real ones, ``quota_refusal`` runs for real, and a creation path that
    forgets to meter itself is refused here exactly as it would be in
    production. What this fixture removes is not the wall; it is the shared
    database underneath it.

    ``TestingConfig.DB_NAME`` resolves once per pytest process, so one
    SQLite file carries every tenant, team and admin the whole run creates.
    By the fiftieth test there are fifty tenants in it, and a Free licence's
    limit of 1 refuses everything — not because the test did anything wrong
    but because earlier tests existed. Counting from a per-test baseline
    makes each test see the deployment it actually built.

    This replaces a session-scoped fixture that resolved every limit as
    Enterprise. That one *was* a relaxation of the gate: with every wall
    unlimited, ``quota_refusal`` returned ``None`` before it looked at
    anything, so no route outside ``test_quotas.py`` could observe a missing
    meter. It is why ``POST /api/v1/auth/register`` creating an unmetered
    team survived review — the only file that could have caught it was the
    one file that overrode the fixture.

    Tests that legitimately build a multi-tenant or delegated-admin
    structure ask for :func:`enterprise_license`, which is what a customer
    doing the same thing would have to buy.
    """
    from app import quotas

    baselines: dict[str, int] = {}

    def _relative(name: str) -> Any:
        real = getattr(quotas, name)

        async def _counter(*args: Any) -> int:
            actual = int(await real(*args))
            base = baselines.setdefault(f"{name}{args!r}", actual)
            return max(actual - base, 0)

        return _counter

    for counter in _ACCUMULATING_COUNTERS:
        monkeypatch.setattr(quotas, counter, _relative(counter))


class _FakeFlagServer:
    """A PostHog stand-in that answers "the products are switched on".

    Not a relaxation of the product gate: ``app.flags`` runs in full — the
    conjunction, the cache, the unknown-flag rule and the degradation paths
    all execute against this exactly as against a real server. What it
    supplies is the flag STATE, and "every product enabled" is the state a
    working deployment is in. With no PostHog configured every flag resolves
    to its default (OFF), so without this the suite would be testing a
    portal with every module switched off, which nobody runs.

    Licensed FEATURE flags are deliberately left unknown (``None``), so they
    keep resolving to OFF and nothing is silently entitled by this fixture.
    ``tests/api/test_flags.py`` drives the gate from both sides explicitly.
    """

    def __init__(self, enabled: "frozenset[str]") -> None:
        self._enabled = enabled

    def feature_enabled(self, key: str, distinct_id: str) -> bool | None:
        feature = key.split(".", 1)[-1]
        return True if feature in self._enabled else None

    def get_all_flags(self, distinct_id: str) -> dict[str, bool]:
        return {f"penguincloud.{feature}": True for feature in self._enabled}


@pytest.fixture(autouse=True)
def _product_flags_enabled(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Model a deployment whose product modules are turned on.

    Installed as the client the real ``get_client`` hands out, rather than
    by replacing ``get_client`` itself, so every line of that function still
    runs — including the "no key configured" path a test can reach by
    calling ``flags.reset_client()``.
    """
    from app import flags

    flags.reset_client()
    monkeypatch.setattr(flags, "_client", _FakeFlagServer(flags.PRODUCT_FLAGS))
    monkeypatch.setattr(flags, "_client_built", True)
    yield
    flags.reset_client()


@pytest.fixture
def enterprise_license(monkeypatch: pytest.MonkeyPatch) -> None:
    """Licence this test at Enterprise — tier, entitlements and limits.

    Opt-in, never automatic. A test asks for this when the structure it
    builds — a tenant hierarchy, a delegated admin, a second team — is the
    structure the licence sells. Requesting it is a statement that the test
    exercises a paid shape, which a reader of the test needs to know anyway.

    All three faces of the licence move together on purpose. A fixture that
    lifted only the numeric walls would leave the capability gates
    (``multi_tenant``, ``delegated_admin``) refusing, so a test would half
    pass and the reason would look like an authorization bug rather than an
    unlicensed one.
    """
    from app import licensing, quotas

    async def _enterprise_license() -> "quotas.TierLimits":
        return quotas.DEFAULT_TIER_LIMITS[licensing.TIER_ENTERPRISE]

    monkeypatch.setattr(quotas, "resolve_limits", _enterprise_license)
    monkeypatch.setattr(
        licensing, "resolve_tier_blocking", lambda: licensing.TIER_ENTERPRISE
    )
    monkeypatch.setattr(
        licensing, "is_feature_entitled_blocking", lambda feature: True
    )
