"""phase 3: campaigns + campaign_tasks

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-20

Additive only (SPEC §8). Zones and rooms.zone_id already exist from
Phase 1's schema-ahead migration, so the zone overlay needs no DDL —
Phase 3 only adds the seasonal-campaign tables.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("season", sa.String(length=50), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "campaign_tasks",
        sa.Column(
            "campaign_id",
            sa.Integer(),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "task_id",
            sa.Integer(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Completion marks a task done across active campaigns — that lookup
    # comes in by task_id, the reverse of the primary key's order.
    op.create_index("ix_campaign_tasks_task_id", "campaign_tasks", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_campaign_tasks_task_id", table_name="campaign_tasks")
    op.drop_table("campaign_tasks")
    op.drop_table("campaigns")
