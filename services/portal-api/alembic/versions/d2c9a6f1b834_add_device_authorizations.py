"""Add device_authorizations -- RFC 8628 device authorization grant.

Backs the CLI (`pcli`) headless login flow (Phase 8): POST .../auth/device/
authorize mints a device_code/user_code pair and inserts a pending row here;
POST .../auth/device/approve or .../deny (authenticated, human in a browser)
resolves it; POST .../auth/device/token (unauthenticated, polled by the CLI)
consumes it exactly once. See app.device_auth's module docstring for the
full state machine and app.models_sqlalchemy.DeviceAuthorization for the
column-level rationale (device_code stored hashed, user_code stored
plaintext, tenant_id always NULL until login itself supports tenant
selection).

Revision ID: d2c9a6f1b834
Revises: f4358cd0f8de
Create Date: 2026-08-31 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2c9a6f1b834"
down_revision: str | None = "f4358cd0f8de"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the device_authorizations table."""
    op.create_table(
        "device_authorizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_code_hash", sa.String(length=64), nullable=False),
        sa.Column("user_code", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_polled_at", sa.DateTime(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'denied', 'consumed')",
            name="ck_device_authorizations_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_code_hash", name="uq_device_authorizations_device_code_hash"),
        sa.UniqueConstraint("user_code", name="uq_device_authorizations_user_code"),
    )


def downgrade() -> None:
    """Drop the device_authorizations table."""
    op.drop_table("device_authorizations")
