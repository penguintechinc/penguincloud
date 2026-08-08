"""Add hierarchical tenancy schema

Revision ID: e94b513398d4
Revises: f1bbaa47eed6
Create Date: 2026-08-07 21:04:47.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e94b513398d4"
down_revision: Union[str, None] = "f1bbaa47eed6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add hierarchical tenancy columns and tables."""
    # batch_alter_table, not bare op.add_column: adding a column that carries
    # a ForeignKey emits an ALTER ... ADD CONSTRAINT, which SQLite does not
    # support at all ("No support for ALTER of constraints in SQLite
    # dialect"). Batch mode's copy-and-move strategy covers SQLite and
    # degrades to a plain ALTER on PostgreSQL/MySQL, so one code path serves
    # every supported backend. Without this, `alembic upgrade head` could
    # never complete on the SQLite development/test backend.
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.add_column(
            sa.Column(
                "parent_tenant_id",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "kind",
                sa.String(length=50),
                server_default="customer",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "depth",
                sa.Integer(),
                server_default=sa.text("0"),
                nullable=False,
            )
        )
        batch_op.create_foreign_key(
            "fk_tenants_parent_tenant_id",
            "tenants",
            ["parent_tenant_id"],
            ["id"],
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
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.drop_constraint("fk_tenants_parent_tenant_id", type_="foreignkey")
        batch_op.drop_column("depth")
        batch_op.drop_column("kind")
        batch_op.drop_column("parent_tenant_id")
