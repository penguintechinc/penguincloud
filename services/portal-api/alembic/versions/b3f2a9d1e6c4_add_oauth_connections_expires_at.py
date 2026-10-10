"""Add oauth_connections.expires_at -- closes the models.py/schema gap.

app.models.store_oauth_connection (and create_oauth_connection) has always
accepted an ``expires_at`` kwarg and passed it straight to both the insert
and the update against ``db.oauth_connections``, but
app.models_sqlalchemy.OAuthConnection never declared the column.
SQLAlchemy's compiler raises ``CompileError: Unconsumed column names:
expires_at`` for both paths, so every real OAuth sign-in that reaches this
call -- a new user, an existing user linked by email, or a repeat sign-in
linked by provider id -- 500s. This was undiscovered because oauth.py sat
at 31% coverage until a follow-up test pass added tests/api/test_oauth_
flow.py, which xfailed the five call paths that hit this gap.

refresh_token is already stored per connection; expires_at is the field a
future token-refresh flow needs to know when to use it, matching the
pattern already used by refresh_tokens/password_reset_tokens/email_
confirmation_tokens/api_keys (all of which persist expires_at). Nullable,
like api_keys.expires_at, because not every provider's token response
includes ``expires_in``.

Revision ID: b3f2a9d1e6c4
Revises: a7c31f0b9d24
Create Date: 2026-08-22 16:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3f2a9d1e6c4"
down_revision: str | None = "a7c31f0b9d24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable oauth_connections.expires_at column."""
    op.add_column("oauth_connections", sa.Column("expires_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Drop oauth_connections.expires_at."""
    op.drop_column("oauth_connections", "expires_at")
