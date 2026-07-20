"""phase 1 core: zones, rooms, tasks, completion_logs, settings + reminders.task_id

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-20

Additive only (SPEC §8): nothing from 0001 is altered destructively.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "zones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("week_of_month", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "rooms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "zone_id",
            sa.Integer(),
            sa.ForeignKey("zones.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "room_id",
            sa.Integer(),
            sa.ForeignKey("rooms.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("category", sa.String(length=20), nullable=False, server_default="cleaning"),
        sa.Column("cadence_days", sa.Integer(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("effort", sa.String(length=10), nullable=False, server_default="quick"),
        sa.Column("guest_facing", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "assignee_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_tasks_room_id", "tasks", ["room_id"])
    op.create_index("ix_tasks_is_active", "tasks", ["is_active"])

    op.create_table(
        "completion_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "task_id",
            sa.Integer(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "completed_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="direct"),
    )
    op.create_index("ix_completion_logs_task_id", "completion_logs", ["task_id"])
    op.create_index("ix_completion_logs_completed_at", "completion_logs", ["completed_at"])

    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", "key", name="uq_settings_user_key"),
    )

    op.add_column(
        "reminders",
        sa.Column(
            "task_id",
            sa.Integer(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_reminders_task_id", "reminders", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_reminders_task_id", table_name="reminders")
    op.drop_column("reminders", "task_id")
    op.drop_table("settings")
    op.drop_index("ix_completion_logs_completed_at", table_name="completion_logs")
    op.drop_index("ix_completion_logs_task_id", table_name="completion_logs")
    op.drop_table("completion_logs")
    op.drop_index("ix_tasks_is_active", table_name="tasks")
    op.drop_index("ix_tasks_room_id", table_name="tasks")
    op.drop_table("tasks")
    op.drop_table("rooms")
    op.drop_table("zones")
