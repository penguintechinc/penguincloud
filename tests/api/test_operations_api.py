"""Portal operation endpoints: the routes the UI polls.

Covers the HTTP layer added alongside the ``Operation`` contract — auth
ordering, the kill switch, scope separation between polling and cancelling,
and the response shape a refetch loop branches on.

The adapter itself is stubbed here. What the adapter does with Gough is
already covered exhaustively in ``test_gough_adapter.py``; repeating it
through the HTTP layer would test httpx twice and the route logic once.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Iterator
from unittest import mock

import pytest
from quart import Quart

from app.adapters.base import (
    AdapterCapabilityError,
    Operation,
    OperationLogLine,
    OperationState,
    Page,
    ResourceConflictError,
)

PRODUCT_SECRET = "-".join(("not", "a", "real", "operations", "credential"))

#: Patch target for scope resolution. `has_tenant_scope` looks the name up on
#: `app.authz` at call time, so this is the binding that has to be replaced.
_AUTHZ_MODULE = "app.authz"


async def _register(client: Any) -> tuple[int, str]:
    """Register a user; return (id, email)."""
    email = f"ops-{uuid.uuid4().hex[:8]}@example.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "testpass123", "full_name": "Ops User"},
    )
    assert response.status_code in (200, 201), await response.get_json()
    return int((await response.get_json())["user"]["id"]), email


async def _headers(client: Any, email: str) -> dict[str, str]:
    """Log in and build Authorization headers."""
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "testpass123"}
    )
    assert response.status_code == 200, await response.get_json()
    return {"Authorization": f"Bearer {(await response.get_json())['access_token']}"}


async def _create_tenant(client: Any, headers: dict[str, str]) -> int:
    """Create a tenant owned by the caller."""
    response = await client.post(
        "/api/v1/tenants",
        headers=headers,
        json={
            "name": "Ops",
            "slug": f"ops-{uuid.uuid4().hex[:6]}",
            "plan": "free",
        },
    )
    assert response.status_code == 201, await response.get_json()
    return int((await response.get_json())["id"])


async def _create_connection(app: Quart, tenant_id: int) -> int:
    """Create an active Gough connection plus its tenant mapping."""
    async with app.app_context():
        from app.models import create_product_connection, set_product_tenant_map

        conn_id = await create_product_connection(
            tenant_id=tenant_id,
            product_type="gough",
            display_name="Ops Gough",
            base_url="https://product.invalid",
            auth_type="bearer",
            api_key=PRODUCT_SECRET,
            api_secret="",
        )
        assert conn_id is not None
        await set_product_tenant_map(conn_id, tenant_id, "tenant_id", "ext-ops")
        return int(conn_id)


@contextmanager
def _patched_scopes(replacement: Any) -> Iterator[None]:
    """Run a block with a specific scope set granted to every caller.

    Patched at ``app.authz.resolve_scopes`` — the name ``has_tenant_scope``
    actually calls — rather than at its definition, so the substitution is
    effective regardless of how the module imported it. The real
    :class:`~app.adapters.base.RBACEnforcer` still decides whether the granted
    set satisfies the requirement, so the coarse-implies-per-product relation
    is exercised for real rather than stubbed.

    Uses ``mock.patch`` with a STRING target rather than assigning to the
    module attribute: ``mypy --strict`` rejects the assignment form with
    "Module does not explicitly export attribute", and the pre-commit hook
    runs mypy on staged test files.
    """
    with mock.patch(f"{_AUTHZ_MODULE}.resolve_scopes", replacement):
        yield


def _operation(**overrides: Any) -> Operation:
    """A running deployment."""
    defaults: dict[str, Any] = {
        "id": "77",
        "kind": "deployment",
        "state": OperationState.RUNNING,
        "status": "in_progress",
        "resource_id": "12",
        "resource_kind": "nodes",
        "progress": None,
        "detail": "phase 2",
        "created_at": datetime(2026, 8, 6, 12, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 8, 6, 12, 5, tzinfo=UTC),
    }
    defaults.update(overrides)
    return Operation(**defaults)


class StubAdapter:
    """Adapter double recording the ctx it was handed."""

    seen_ctx: Any = None
    seen_filters: dict[str, Any] = {}
    operation: Operation | None = None
    raises: Exception | None = None
    logs: list[OperationLogLine] = []

    def __init__(self) -> None:
        """Match the registry's zero-argument construction."""

    async def get_operation(self, kind: str, operation_id: str, ctx: Any) -> Operation:
        """Return the staged operation or raise the staged error."""
        StubAdapter.seen_ctx = ctx
        if StubAdapter.raises is not None:
            raise StubAdapter.raises
        assert StubAdapter.operation is not None
        return StubAdapter.operation

    async def cancel_operation(
        self, kind: str, operation_id: str, ctx: Any
    ) -> Operation:
        """Return the staged operation or raise the staged error."""
        StubAdapter.seen_ctx = ctx
        if StubAdapter.raises is not None:
            raise StubAdapter.raises
        assert StubAdapter.operation is not None
        return StubAdapter.operation

    async def list_operations(self, ctx: Any, **kwargs: Any) -> Page[Operation]:
        """Return a single-item page, recording the filters supplied."""
        StubAdapter.seen_ctx = ctx
        StubAdapter.seen_filters = kwargs
        if StubAdapter.raises is not None:
            raise StubAdapter.raises
        assert StubAdapter.operation is not None
        return Page(items=[StubAdapter.operation], page=1, per_page=20)

    async def operation_logs(self, *args: Any, **kwargs: Any) -> list[OperationLogLine]:
        """Return the staged log lines."""
        if StubAdapter.raises is not None:
            raise StubAdapter.raises
        return StubAdapter.logs


@pytest.fixture(autouse=True)
def _stub_adapter(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Swap the Gough adapter for the stub, and reset staged state."""
    StubAdapter.operation = _operation()
    StubAdapter.raises = None
    StubAdapter.logs = []
    StubAdapter.seen_ctx = None
    monkeypatch.setitem(
        __import__("app.adapters", fromlist=["ADAPTER_REGISTRY"]).ADAPTER_REGISTRY,
        "gough",
        StubAdapter,
    )
    return StubAdapter


async def _setup(client: Any, app: Quart) -> tuple[int, dict[str, str]]:
    """Register, create a tenant and a connection; return (conn_id, headers)."""
    _, email = await _register(client)
    headers = await _headers(client, email)
    tenant_id = await _create_tenant(client, headers)
    conn_id = await _create_connection(app, tenant_id)
    return conn_id, headers


@pytest.mark.asyncio
class TestPolling:
    """The refetch loop's contract with the portal."""

    async def test_poll_returns_the_flag_the_ui_branches_on(
        self, client: Any, app: Quart
    ) -> None:
        """``is_terminal`` is published, not left for the client to derive.

        Every consumer deriving it re-implements the terminal-state set, and
        one of them gets it wrong — polling a finished operation forever or
        dropping a live one.
        """
        conn_id, headers = await _setup(client, app)

        response = await client.get(
            f"/api/v1/products/{conn_id}/operations/deployment/77", headers=headers
        )

        assert response.status_code == 200
        body = await response.get_json()
        assert body["state"] == "running"
        assert body["is_terminal"] is False
        assert body["status"] == "in_progress"
        assert body["resource_id"] == "12"

    async def test_terminal_operation_reports_terminal(
        self, client: Any, app: Quart
    ) -> None:
        """A succeeded operation must stop the poll loop."""
        conn_id, headers = await _setup(client, app)
        StubAdapter.operation = _operation(
            state=OperationState.SUCCEEDED,
            status="succeeded",
            completed_at=datetime(2026, 8, 6, 12, 9, tzinfo=UTC),
        )

        response = await client.get(
            f"/api/v1/products/{conn_id}/operations/deployment/77", headers=headers
        )

        body = await response.get_json()
        assert body["is_terminal"] is True
        assert body["completed_at"] is not None

    async def test_response_publishes_only_declared_fields(
        self, client: Any, app: Quart
    ) -> None:
        """The wire shape is an explicit DTO, not the dataclass.

        ``Operation.metadata`` carries product internals — Gough puts biome
        ids, log URLs and node ids there. Serialising the dataclass directly
        would publish whatever a future field happened to hold.
        """
        conn_id, headers = await _setup(client, app)
        StubAdapter.operation = _operation(
            metadata={"logs_url": "/internal/secret", "biome_id": 5}
        )

        response = await client.get(
            f"/api/v1/products/{conn_id}/operations/deployment/77", headers=headers
        )

        body = await response.get_json()
        assert "metadata" not in body
        assert "/internal/secret" not in str(body)
        assert set(body) == {
            "id",
            "kind",
            "state",
            "status",
            "is_terminal",
            "resource_id",
            "resource_kind",
            "progress",
            "detail",
            "error",
            # I4: the success counterpart of `error`. Nest's snapshot/restore/
            # migrate finish by producing an artefact and had nowhere to
            # report it; `metadata` is not that place, because this DTO
            # deliberately does not publish it.
            "result",
            "created_at",
            "updated_at",
            "completed_at",
        }

    async def test_result_is_published_and_metadata_still_is_not(
        self, client: Any, app: Quart
    ) -> None:
        """I4: a produced artefact reaches the wire; internals still do not.

        Both halves matter. Publishing `result` is what gives an adapter a
        declared channel for what an operation made; keeping `metadata`
        unpublished is what stops that channel from becoming "serialise
        everything".
        """
        conn_id, headers = await _setup(client, app)
        StubAdapter.operation = _operation(
            state=OperationState.SUCCEEDED,
            status="succeeded",
            result={"snapshot_id": "snap-42", "bytes": 1024},
            metadata={"logs_url": "/internal/secret"},
        )

        response = await client.get(
            f"/api/v1/products/{conn_id}/operations/deployment/77", headers=headers
        )

        body = await response.get_json()
        assert body["result"] == {"snapshot_id": "snap-42", "bytes": 1024}
        assert "metadata" not in body
        assert "/internal/secret" not in str(body)

    async def test_result_is_null_when_the_operation_produced_nothing(
        self, client: Any, app: Quart
    ) -> None:
        """Absent, not omitted — a caller can tell "none" from "not sent"."""
        conn_id, headers = await _setup(client, app)
        StubAdapter.operation = _operation()

        response = await client.get(
            f"/api/v1/products/{conn_id}/operations/deployment/77", headers=headers
        )

        body = await response.get_json()
        assert "result" in body
        assert body["result"] is None

    async def test_capability_error_is_501_not_500(
        self, client: Any, app: Quart
    ) -> None:
        """An unsupported operation kind is a declared absence."""
        conn_id, headers = await _setup(client, app)
        StubAdapter.raises = AdapterCapabilityError("gough has no operation kind 'x'")

        response = await client.get(
            f"/api/v1/products/{conn_id}/operations/x/77", headers=headers
        )

        assert response.status_code == 501

    async def test_list_rejects_an_unknown_state_filter(
        self, client: Any, app: Quart
    ) -> None:
        """A bad filter is the caller's error, not an upstream failure."""
        conn_id, headers = await _setup(client, app)

        response = await client.get(
            f"/api/v1/products/{conn_id}/operations?state=wibble", headers=headers
        )

        assert response.status_code == 400
        assert "running" in (await response.get_json())["allowed"]

    async def test_per_page_is_capped(self, client: Any, app: Quart) -> None:
        """A poll loop must not be able to ask for unbounded pages."""
        conn_id, headers = await _setup(client, app)

        response = await client.get(
            f"/api/v1/products/{conn_id}/operations?per_page=100000", headers=headers
        )

        assert response.status_code == 200
        assert StubAdapter.seen_filters["per_page"] == 100


@pytest.mark.asyncio
class TestAuthorization:
    """Who may poll, who may cancel, and what a deactivated connection does."""

    async def test_cancel_requires_manage_and_reads_require_read(
        self, client: Any, app: Quart
    ) -> None:
        """Cancelling a deploy changes what the product does with hardware.

        Behavioural now, not source inspection. The previous version grepped
        each handler for ``SCOPE_PRODUCTS_MANAGE``; that could only ever check
        which *constant name* was typed, so it passed while the routes were
        gated on the coarse scope and would have kept passing if the required
        scope had been renamed but not enforced.
        """
        conn_id, headers = await _setup(client, app)

        granted: list[str] = []

        async def _only(user_id: int, tenant_id: int) -> list[str]:
            return list(granted)

        with _patched_scopes(_only):
            granted[:] = ["products:gough:read"]
            poll = await client.get(
                f"/api/v1/products/{conn_id}/operations/deployment/77",
                headers=headers,
            )
            cancel = await client.post(
                f"/api/v1/products/{conn_id}/operations/deployment/77/cancel",
                headers=headers,
            )

        assert poll.status_code == 200
        assert cancel.status_code == 403, "read scope reached a mutating route"

    async def test_a_gough_only_scope_drives_gough_operations(
        self, client: Any, app: Quart
    ) -> None:
        """I3: the per-product model must not stop at the proxy.

        The principal these scopes exist for holds ``products:gough:manage``
        and no coarse grant. Before this fix the operations routes required
        ``products:read``/``products:manage``, so that principal could start a
        deploy through the proxy and was then refused permission to poll it,
        cancel it, or read its logs.
        """
        conn_id, headers = await _setup(client, app)

        async def _gough_only(user_id: int, tenant_id: int) -> list[str]:
            return ["products:gough:read", "products:gough:manage"]

        with _patched_scopes(_gough_only):
            listed = await client.get(
                f"/api/v1/products/{conn_id}/operations", headers=headers
            )
            polled = await client.get(
                f"/api/v1/products/{conn_id}/operations/deployment/77",
                headers=headers,
            )
            logs = await client.get(
                f"/api/v1/products/{conn_id}/operations/deployment/77/logs",
                headers=headers,
            )
            cancelled = await client.post(
                f"/api/v1/products/{conn_id}/operations/deployment/77/cancel",
                headers=headers,
            )

        assert listed.status_code == 200
        assert polled.status_code == 200
        assert logs.status_code == 200
        assert cancelled.status_code == 200

    async def test_another_products_scope_cannot_touch_a_gough_operation(
        self, client: Any, app: Quart
    ) -> None:
        """Selectivity, the direction that actually proves the gate.

        A scope for a different product must not open this connection. Without
        this half, granting every per-product scope would look identical to
        granting the right one.
        """
        conn_id, headers = await _setup(client, app)
        StubAdapter.seen_ctx = None

        async def _nest_only(user_id: int, tenant_id: int) -> list[str]:
            return ["products:nest:read", "products:nest:manage"]

        with _patched_scopes(_nest_only):
            polled = await client.get(
                f"/api/v1/products/{conn_id}/operations/deployment/77",
                headers=headers,
            )
            cancelled = await client.post(
                f"/api/v1/products/{conn_id}/operations/deployment/77/cancel",
                headers=headers,
            )

        assert polled.status_code == 403
        assert cancelled.status_code == 403
        assert StubAdapter.seen_ctx is None, "adapter was reached without scope"

    async def test_coarse_scope_still_satisfies_the_per_product_form(
        self, client: Any, app: Quart
    ) -> None:
        """The implication is what makes this change non-breaking.

        Every existing tenant admin holds only the coarse grant, so if the
        per-product requirement did not accept it, this fix would have locked
        out every current operator.
        """
        conn_id, headers = await _setup(client, app)

        async def _coarse(user_id: int, tenant_id: int) -> list[str]:
            return ["products:read", "products:manage"]

        with _patched_scopes(_coarse):
            polled = await client.get(
                f"/api/v1/products/{conn_id}/operations/deployment/77",
                headers=headers,
            )
            cancelled = await client.post(
                f"/api/v1/products/{conn_id}/operations/deployment/77/cancel",
                headers=headers,
            )

        assert polled.status_code == 200
        assert cancelled.status_code == 200

    async def test_cancel_conflict_is_409(self, client: Any, app: Quart) -> None:
        """Cancelling a finished operation is a conflict, not a server error."""
        conn_id, headers = await _setup(client, app)
        StubAdapter.raises = ResourceConflictError("already succeeded")

        response = await client.post(
            f"/api/v1/products/{conn_id}/operations/deployment/77/cancel",
            headers=headers,
        )

        assert response.status_code == 409

    async def test_unauthenticated_caller_is_refused(
        self, client: Any, app: Quart
    ) -> None:
        """No token, no operation."""
        conn_id, _ = await _setup(client, app)

        response = await client.get(
            f"/api/v1/products/{conn_id}/operations/deployment/77"
        )

        assert response.status_code == 401

    async def test_non_member_cannot_poll_another_tenants_operation(
        self, client: Any, app: Quart
    ) -> None:
        """An outsider learns nothing, and the adapter is never reached."""
        conn_id, _ = await _setup(client, app)
        _, outsider_email = await _register(client)
        outsider_headers = await _headers(client, outsider_email)
        StubAdapter.seen_ctx = None

        response = await client.get(
            f"/api/v1/products/{conn_id}/operations/deployment/77",
            headers=outsider_headers,
        )

        # M6: EXACTLY 404, not "403 or 404". The looseness was hiding a
        # cross-tenant existence oracle: a 403 answers "this id exists, in a
        # tenant that is not yours" and a 404 answers "no such id", so an
        # assertion accepting either passes whichever one the code emits and
        # can never detect the disclosure. A non-member must not be able to
        # tell an existing connection from an absent one.
        assert response.status_code == 404
        assert StubAdapter.seen_ctx is None, "adapter was reached by a non-member"

    async def test_deactivated_connection_is_refused_before_decryption(
        self, client: Any, app: Quart
    ) -> None:
        """The products UI offers a kill switch; it has to stop this path too.

        An operation route that ignored ``is_active`` would keep polling and
        cancelling against a connection an operator believes they stopped.
        """
        conn_id, headers = await _setup(client, app)
        async with app.app_context():
            from app.models import get_db

            db = get_db()
            await db(db.product_connections.id == conn_id).update(is_active=False)
            await db.commit()
        StubAdapter.seen_ctx = None

        response = await client.get(
            f"/api/v1/products/{conn_id}/operations/deployment/77", headers=headers
        )

        assert response.status_code == 403
        assert StubAdapter.seen_ctx is None


@pytest.mark.asyncio
class TestLogs:
    """The DetailDrawer's log tab."""

    async def test_logs_are_typed_and_ordered(self, client: Any, app: Quart) -> None:
        """Level and timestamp are separate fields, not embedded in the text."""
        conn_id, headers = await _setup(client, app)
        StubAdapter.logs = [
            OperationLogLine(
                message="starting",
                level="info",
                timestamp=datetime(2026, 8, 6, 12, 0, tzinfo=UTC),
            ),
            OperationLogLine(message="pull failed", level="error"),
        ]

        response = await client.get(
            f"/api/v1/products/{conn_id}/operations/deployment/77/logs?tail=25",
            headers=headers,
        )

        assert response.status_code == 200
        body = await response.get_json()
        assert [line["message"] for line in body["logs"]] == ["starting", "pull failed"]
        assert body["logs"][1]["level"] == "error"
        assert body["logs"][1]["timestamp"] is None

    async def test_malformed_since_is_a_client_error(
        self, client: Any, app: Quart
    ) -> None:
        """An unparseable timestamp must not reach the product."""
        conn_id, headers = await _setup(client, app)

        response = await client.get(
            f"/api/v1/products/{conn_id}/operations/deployment/77/logs?since=yesterday",
            headers=headers,
        )

        assert response.status_code == 400
