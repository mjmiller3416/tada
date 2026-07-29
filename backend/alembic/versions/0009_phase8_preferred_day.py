"""phase 8: preferred-day boost

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-29

Additive only (SPEC §8): one nullable column on tasks. `preferred_day`
uses Python's weekday() convention (Monday = 0 ... Sunday = 6); null —
the default and the overwhelmingly common case — means no preference.

This is a BOOST, not a schedule (SPEC §1: decay, not a calendar): the
column feeds a ranking boost in services/scheduling.py and nothing
else. No due dates, no overdue state, no reminders hang off it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("preferred_day", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "preferred_day")
