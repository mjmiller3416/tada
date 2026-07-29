"""phase 5: badges + user_badges

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-29

Additive only (SPEC §8): two new tables, nothing existing altered.
The streak fields this phase starts writing (current_streak,
longest_streak, last_active_date) have lived on users since Phase 0.
Badge rows themselves are seeded idempotently by services/badges.py,
matching how the packing templates and FlyLady zones seed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "badges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("emoji", sa.String(length=16), nullable=False),
        sa.Column("criteria_key", sa.String(length=50), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("code", name="uq_badges_code"),
    )
    op.create_table(
        "user_badges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "badge_id",
            sa.Integer(),
            sa.ForeignKey("badges.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("earned_at", sa.DateTime(timezone=True), nullable=False),
        # Earned once, never revoked (SPEC §5: you can never lose a badge).
        sa.UniqueConstraint("user_id", "badge_id", name="uq_user_badges_user_badge"),
    )


def downgrade() -> None:
    op.drop_table("user_badges")
    op.drop_table("badges")
