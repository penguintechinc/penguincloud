"""What the audit surfaces publish, asserted field by field.

All four projections of ``audit_logs`` returned ``dict(row)`` — the raw
database record — except one hand-curated list. ``security.md`` names this
exact failure and requires a regression test for any endpoint that has
over-exposed data, one that fails on an EXTRA field and not only a missing
one:

    a bug meant an endpoint that was only supposed to return a single string
    ended up returning the entire database object it came from ... Nothing
    crashed, no error, no signal anything was wrong.

The stakes here are set by the licensing ruling: ``/api/v1/dashboard/
activity`` is reachable on EVERY tier, and it was serving the widest
projection of the most sensitive table in the portal.

Two layers, deliberately
========================
* :class:`TestThePublishedFieldSetIsPinned` asserts the DTO's fields as
  LITERAL names. This is the test that fails if someone adds ``request_body``
  to :class:`app.audit_view.AuditRecord`.
* :class:`TestEveryAuditSurfaceMatchesTheDto` asserts each route's live
  response equals the DTO's field set. This is the test that fails if a
  route stops projecting.

Deriving both from the DTO would let a single edit move both sides at once,
which is how a schema check comes to assert only that a program agrees with
itself.
"""

from __future__ import annotations

import csv
import io
import uuid
from typing import Any

import pytest
from app.audit_view import AUDIT_RECORD_FIELDS, AuditRecord
from penguin_dal.quart_ext import get_db
from quart import Quart

pytestmark = pytest.mark.usefixtures("enterprise_license")

#: Columns on ``audit_logs`` that must never reach a response body.
#:
#: ``request_body`` is the one that matters: it is the submitted payload, so
#: it can carry credentials, tokens and PII. Nothing populates it today,
#: which is precisely why the exclusion is worth pinning now — the first
#: writer that starts filling it would otherwise publish it through four
#: endpoints at once with no code change near any of them.
FORBIDDEN_AUDIT_COLUMNS = frozenset(
    {"request_body", "user_agent", "response_status", "metadata", "metadata_json"}
)


async def _seed(app: Quart, tenant_id: int, marker: str) -> None:
    """Insert one audit row with every sensitive column populated."""
    async with app.app_context():
        db = get_db()
        await db.audit_logs.async_insert(
            user_id=None,
            tenant_id=tenant_id,
            action_type="secret.action",
            resource_type="secret_resource",
            resource_id=marker,
            ip_address="203.0.113.9",
            user_agent="Mozilla/5.0 (fingerprintable)",
            request_body='{"password": "hunter2", "token": "sk-not-a-real-one"}',
            response_status=200,
        )


class TestThePublishedFieldSetIsPinned:
    """The DTO itself, as literal names. Adding a field must fail here."""

    def test_exact_field_set(self) -> None:
        """Every published field, spelled out.

        Not derived from the dataclass — that would assert only that the
        code agrees with itself. Changing this list is the deliberate act;
        the failure is the review prompt.
        """
        assert set(AUDIT_RECORD_FIELDS) == {
            "id",
            "user_id",
            "action",
            "resource_type",
            "resource_id",
            "tenant_id",
            "product_connection_id",
            "ip_address",
            "created_at",
        }

    @pytest.mark.parametrize("column", sorted(FORBIDDEN_AUDIT_COLUMNS))
    def test_a_sensitive_column_is_not_published(self, column: str) -> None:
        """request_body can hold credentials; none of these are renderable."""
        assert column not in AUDIT_RECORD_FIELDS

    def test_the_dto_is_frozen_and_slotted(self) -> None:
        """A slotted frozen DTO cannot acquire a field at runtime."""
        record = AuditRecord(
            id=1,
            user_id=None,
            action="a",
            resource_type=None,
            resource_id=None,
            tenant_id=None,
            product_connection_id=None,
            ip_address=None,
            created_at=None,
        )
        with pytest.raises((AttributeError, TypeError)):
            record.request_body = "leaked"  # type: ignore[attr-defined]


@pytest.mark.asyncio
class TestEveryAuditSurfaceMatchesTheDto:
    """Live responses, with a row whose sensitive columns are populated."""

    async def test_dashboard_activity(
        self, client: Any, app: Quart, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """The least-gated audit surface, reachable on every tier."""
        marker = f"act-{uuid.uuid4().hex[:8]}"
        await _seed(app, tenant_id, marker)

        response = await client.get(
            f"/api/v1/dashboard/activity?tenant_id={tenant_id}&limit=100",
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = await response.get_json()
        rows = body["activity"]
        assert rows, "seeded row not returned — the assertion below is vacuous"
        for row in rows:
            assert set(row) == set(AUDIT_RECORD_FIELDS)

        # The badge reads `action`; the raw row only ever had `action_type`,
        # so this feed rendered undefined until the projection landed.
        assert any(row["action"] == "secret.action" for row in rows)
        blob = str(body)
        assert "hunter2" not in blob
        assert "sk-not-a-real-one" not in blob
        assert "fingerprintable" not in blob

    async def test_audit_logs(
        self, client: Any, app: Quart, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """The Enterprise query surface."""
        marker = f"logs-{uuid.uuid4().hex[:8]}"
        await _seed(app, tenant_id, marker)

        response = await client.get(
            f"/api/v1/audit/logs?tenant_id={tenant_id}", headers=admin_headers
        )

        assert response.status_code == 200
        body = await response.get_json()
        assert body["logs"], "seeded row not returned"
        for row in body["logs"]:
            assert set(row) == set(AUDIT_RECORD_FIELDS)
        assert "hunter2" not in str(body)

    async def test_audit_export_json(
        self, client: Any, app: Quart, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """The Enterprise export, JSON."""
        marker = f"exp-{uuid.uuid4().hex[:8]}"
        await _seed(app, tenant_id, marker)

        response = await client.get(
            f"/api/v1/audit/export?tenant_id={tenant_id}&format=json",
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = await response.get_json()
        assert body["logs"], "seeded row not returned"
        for row in body["logs"]:
            assert set(row) == set(AUDIT_RECORD_FIELDS)
        assert "hunter2" not in str(body)

    async def test_audit_export_csv_columns(
        self, client: Any, app: Quart, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """The CSV took its columns from ``records[0].keys()``.

        So it exported whatever the row happened to carry, into a file the
        customer downloads and keeps. A column added to the schema would
        have started appearing there with no code change near this route.
        """
        marker = f"csv-{uuid.uuid4().hex[:8]}"
        await _seed(app, tenant_id, marker)

        response = await client.get(
            f"/api/v1/audit/export?tenant_id={tenant_id}&format=csv",
            headers=admin_headers,
        )

        assert response.status_code == 200
        text = (await response.get_data()).decode()
        header = next(csv.reader(io.StringIO(text)))

        assert header == list(AUDIT_RECORD_FIELDS)
        assert "hunter2" not in text
        assert "fingerprintable" not in text

    async def test_users_audit_logs(
        self, client: Any, app: Quart, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """The fourth surface, whose curated list is now the shared one."""
        marker = f"usr-{uuid.uuid4().hex[:8]}"
        await _seed(app, tenant_id, marker)

        response = await client.get(
            f"/api/v1/users/audit-logs?tenant_id={tenant_id}", headers=admin_headers
        )

        assert response.status_code == 200
        body = await response.get_json()
        assert body["logs"], "seeded row not returned"
        for row in body["logs"]:
            assert set(row) == set(AUDIT_RECORD_FIELDS)
        assert "hunter2" not in str(body)
