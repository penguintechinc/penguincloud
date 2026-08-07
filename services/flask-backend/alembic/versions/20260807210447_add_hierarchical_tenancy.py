"""Add hierarchical tenancy schema

Revision ID: 20260807210447
Revises: f1bbaa47eed6
Create Date: 2026-08-07 21:04:47.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260807210447"
down_revision: Union[str, None] = "f1bbaa47eed6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add hierarchical tenancy columns and tables."""
    # Add hierarchical tenancy columns to tenants table
    op.add_column(
        "tenants",
        sa.Column(
            "parent_tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "kind",
            sa.String(length=50),
            server_default="customer",
            nullable=False,
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "depth",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )

    # Create product_tenant_map table
    op.create_table(
        "product_tenant_map",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column(
            "external_kind",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["connection_id"], ["product_connections.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connection_id", "tenant_id"),
    )


def downgrade() -> None:
    """Remove hierarchical tenancy columns and tables."""
    op.drop_table("product_tenant_map")
    op.drop_column("tenants", "depth")
    op.drop_column("tenants", "kind")
    op.drop_column("tenants", "parent_tenant_id")
