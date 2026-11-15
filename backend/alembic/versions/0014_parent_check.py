"""parent check: "ready to check", "checked" and "sent back"

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-14

Additive only (SPEC §8). A parent can ask that a chore be inspected
before it counts as checked:

- `tasks.needs_check` — the per-task opt-in, default false, so every
  existing task behaves exactly as before until a parent turns it on.
- `completion_logs.check_status` — NULL for an ordinary completion (all
  existing rows), else "ready" (done, waiting for a parent to look),
  "checked" (a parent physically inspected and approved it) or
  "sent_back" (not up to standard; the decay reset was reversed).
- `checked_by` / `checked_at` — the parent who checked or sent it back,
  and when. `check_note` — the optional note sent back with it.

The state lives on the completion row because a check is a verdict on
one specific completion: the kid's claim and the parent's inspection
belong to the same event, and history keeps both.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "needs_check",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Batch mode: plain ALTERs on Postgres; on SQLite (tests) the
    # copy-and-move it needs to add a foreign key.
    with op.batch_alter_table("completion_logs") as batch:
        batch.add_column(sa.Column("check_status", sa.String(20), nullable=True))
        batch.add_column(sa.Column("checked_by", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("check_note", sa.Text(), nullable=True))
        batch.create_foreign_key(
            "fk_completion_logs_checked_by_users",
            "users",
            ["checked_by"],
            ["id"],
            ondelete="SET NULL",
        )
        # The parents' "To check" list asks for exactly these rows.
        batch.create_index("ix_completion_logs_check_status", ["check_status"])


def downgrade() -> None:
    with op.batch_alter_table("completion_logs") as batch:
        batch.drop_index("ix_completion_logs_check_status")
        batch.drop_constraint("fk_completion_logs_checked_by_users", type_="foreignkey")
        batch.drop_column("check_note")
        batch.drop_column("checked_at")
        batch.drop_column("checked_by")
        batch.drop_column("check_status")
    op.drop_column("tasks", "needs_check")
