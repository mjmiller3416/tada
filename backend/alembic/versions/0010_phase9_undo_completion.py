"""phase 9: undo a completion

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-29

Additive only (SPEC §8): one nullable column on completion_logs.
`previous_last_done_at` captures the task's last_done_at as it stood the
moment the completion overwrote it, so undo can restore the decay state
exactly. Stored rather than derived from the prior log row because the
Phase 4.6 last-done editor changes last_done_at WITHOUT writing a log —
a log-derived restore would silently discard such a correction.

Rows written before this migration carry NULL here, indistinguishable
from a genuine first-ever completion. Accepted: undo is only offered on
today's completions, so the exposure is the first day after deploy, and
the Phase 4.6 date editor covers the worst case.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "completion_logs",
        sa.Column("previous_last_done_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("completion_logs", "previous_last_done_at")
