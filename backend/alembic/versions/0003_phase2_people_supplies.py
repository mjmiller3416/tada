"""phase 2: supplies + task_supplies, tasks.claimable, users.email nullable

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-20

Additive only (SPEC §8): new tables and columns, plus one widening
(users.email becomes nullable so kid accounts — PIN-only, no email —
fit the existing model).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("users", "email", existing_type=sa.String(length=255), nullable=True)

    op.add_column(
        "tasks",
        sa.Column("claimable", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "supplies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="in_stock"),
        sa.Column("last_pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "task_supplies",
        sa.Column(
            "task_id",
            sa.Integer(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "supply_id",
            sa.Integer(),
            sa.ForeignKey("supplies.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index("ix_task_supplies_supply_id", "task_supplies", ["supply_id"])


def downgrade() -> None:
    op.drop_index("ix_task_supplies_supply_id", table_name="task_supplies")
    op.drop_table("task_supplies")
    op.drop_table("supplies")
    op.drop_column("tasks", "claimable")
    op.alter_column("users", "email", existing_type=sa.String(length=255), nullable=False)
