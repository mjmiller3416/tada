"""phase 4: packing lists

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-20

Additive only (SPEC §8). The packing module is self-contained — three
new tables, deliberately NOT touching the tasks/decay schema (no
cadence, no last_done_at, no dirtiness on packing rows). The single
crossing point is a nullable `packing_list_id` on reminders, so the
existing every-minute cron can send the optional countdown nudge.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "packing_lists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column(
            "is_template", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="active"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "packing_sections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "list_id",
            sa.Integer(),
            sa.ForeignKey("packing_lists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_packing_sections_list_id", "packing_sections", ["list_id"])

    op.create_table(
        "packing_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "section_id",
            sa.Integer(),
            sa.ForeignKey("packing_sections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("quantity", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("packed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_packing_items_section_id", "packing_items", ["section_id"])

    # The countdown reminder's link back to its list. Nullable — every
    # existing reminder kind leaves it empty — and CASCADE so a deleted
    # list can never strand a nudge.
    op.add_column(
        "reminders",
        sa.Column(
            "packing_list_id",
            sa.Integer(),
            sa.ForeignKey("packing_lists.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("reminders", "packing_list_id")
    op.drop_index("ix_packing_items_section_id", table_name="packing_items")
    op.drop_table("packing_items")
    op.drop_index("ix_packing_sections_list_id", table_name="packing_sections")
    op.drop_table("packing_sections")
    op.drop_table("packing_lists")
