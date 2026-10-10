"""Add team_invitations -- closes the models.py/schema gap.

app.teams.send_invitation/accept_invitation/cancel_invitation have always
called db.team_invitations.async_insert/select/update/delete, but no
migration and no app.models_sqlalchemy class ever declared the table.
penguin-dal's AsyncDB.reflect() only exposes tables that actually exist in
the database, so every one of those calls raised ``AttributeError: 'AsyncDB'
object has no attribute 'team_invitations'`` -- the entire team-invitation
feature was dead code behind three otherwise-complete routes. See
tests/api/test_teams.py's TestTeamInvitations xfails (fix/team-invitations
branch) for the exact failure chain this closes.

Shape mirrors password_reset_tokens/email_confirmation_tokens (token,
expires_at, resolved-at column) plus the invitation-specific team_id/email/
role/invited_by_id columns send_invitation already writes and accept_
invitation/cancel_invitation already read.

Revision ID: f4358cd0f8de
Revises: b3f2a9d1e6c4
Create Date: 2026-08-27 18:03:27.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4358cd0f8de"
down_revision: str | None = "b3f2a9d1e6c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the team_invitations table."""
    op.create_table(
        "team_invitations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), server_default="member", nullable=False),
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column("invited_by_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["invited_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_team_invitations_token"),
    )


def downgrade() -> None:
    """Drop the team_invitations table."""
    op.drop_table("team_invitations")
