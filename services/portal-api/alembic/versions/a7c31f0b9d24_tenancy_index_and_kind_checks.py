"""Index tenants.parent_tenant_id and constrain the enumerated kind columns.

Closes the gap between models_sqlalchemy.py and e94b513398d4:

* ``kind``/``external_kind`` were declared as SQLAlchemy ``Enum(PyEnum)`` in
  the ORM but ``String(50)`` in the migration, while penguin-dal writes the
  lowercase member VALUE at runtime. The ORM has been aligned to String; the
  allowed set is now enforced by a CHECK constraint rather than by an
  incompatible native enum type.
* Every hierarchy walk filters ``tenants.parent_tenant_id`` and there was no
  index on it, making each level of both recursive CTEs a full table scan.

Revision ID: a7c31f0b9d24
Revises: e94b513398d4
Create Date: 2026-08-07 18:20:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c31f0b9d24"
down_revision: str | None = "e94b513398d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT_KIND_CHECK = "kind IN ('provider', 'customer')"
_EXTERNAL_KIND_CHECK = "external_kind IN ('tenant_id', 'organization_id', 'namespace')"


def upgrade() -> None:
    """Add the parent index and the enumerated-value CHECK constraints."""
    op.create_index(
        "ix_tenants_parent_tenant_id",
        "tenants",
        ["parent_tenant_id"],
    )

    # batch_alter_table, not a bare ALTER: SQLite cannot ADD CONSTRAINT and
    # requires the table-rebuild strategy. On PostgreSQL/MySQL batch mode
    # emits the plain ALTER, so one code path covers every supported backend.
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.create_check_constraint("ck_tenants_kind", _TENANT_KIND_CHECK)

    with op.batch_alter_table("product_tenant_map") as batch_op:
        batch_op.create_check_constraint(
            "ck_product_tenant_map_external_kind", _EXTERNAL_KIND_CHECK
        )


def downgrade() -> None:
    """Drop the CHECK constraints and the parent index."""
    with op.batch_alter_table("product_tenant_map") as batch_op:
        batch_op.drop_constraint("ck_product_tenant_map_external_kind", type_="check")

    with op.batch_alter_table("tenants") as batch_op:
        batch_op.drop_constraint("ck_tenants_kind", type_="check")

    op.drop_index("ix_tenants_parent_tenant_id", table_name="tenants")
