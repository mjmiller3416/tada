"""packing lists: optional destination and duration

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-20

Additive only (SPEC §8). Two nullable columns on packing_lists so a
list can carry where it's headed and for how long — both optional,
both plain text (duration is a note like "5 days" or "a long
weekend", not math — same philosophy as item quantities).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "packing_lists",
        sa.Column("destination", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "packing_lists",
        sa.Column("duration", sa.String(length=60), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("packing_lists", "duration")
    op.drop_column("packing_lists", "destination")
