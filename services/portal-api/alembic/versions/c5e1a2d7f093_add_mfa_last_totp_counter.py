"""Add mfa_secrets.last_totp_counter -- TOTP replay prevention.

pyotp's ``TOTP.verify`` accepts a code anywhere in its validity window but
does not record that the code was used, so the same 6-digit code could be
replayed (observed over the shoulder, intercepted, or a resent request)
until it aged out. This column records the highest time-step counter already
accepted for a user; app.mfa.verify_totp_code rejects any code whose counter
is <= the stored value and advances it on each success, making every code
single-use.

Nullable: an mfa_secrets row created before a user's first successful
verification has no prior counter, and ``None`` means "nothing accepted
yet" so the first valid code is taken and the column initialised.

Revision ID: c5e1a2d7f093
Revises: d2c9a6f1b834
Create Date: 2026-10-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5e1a2d7f093"
down_revision: str | None = "d2c9a6f1b834"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable mfa_secrets.last_totp_counter column."""
    op.add_column("mfa_secrets", sa.Column("last_totp_counter", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    """Drop mfa_secrets.last_totp_counter."""
    op.drop_column("mfa_secrets", "last_totp_counter")
