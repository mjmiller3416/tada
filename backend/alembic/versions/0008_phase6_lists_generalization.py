"""phase 6: generalize packing into lists

Revision ID: 0008
Revises: 0007

Data-preserving by construction (she has live lists in these tables,
including a 147-item one entered by hand): every table and column change
is a RENAME, never a drop/recreate, so existing rows ride along.

- packing_lists    -> lists          (and category -> kind)
- packing_sections -> list_sections
- packing_items    -> list_items     (+ nullable price, Numeric — never
                                       a float for money)
- reminders.packing_list_id -> reminders.list_id

The 10-value packing category collapses into kind
("packing" | "shopping" | "tasks" | "custom"): everything becomes
"packing" except "custom", which stays "custom". The seeded templates
keep their own names ("Moving", "Travel"), so no identity is lost.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- Tables: rename in place so every row survives ----
    op.rename_table("packing_lists", "lists")
    op.rename_table("packing_sections", "list_sections")
    op.rename_table("packing_items", "list_items")

    # Keep the index names in step with their tables (cosmetic, but a
    # fresh DB and a migrated DB should end up identical).
    op.execute("ALTER INDEX ix_packing_sections_list_id RENAME TO ix_list_sections_list_id")
    op.execute("ALTER INDEX ix_packing_items_section_id RENAME TO ix_list_items_section_id")

    # ---- category -> kind, with the value collapse ----
    op.alter_column("lists", "category", new_column_name="kind")
    op.execute("UPDATE lists SET kind = 'packing' WHERE kind <> 'custom'")

    # ---- The reminders FK follows the rename ----
    op.alter_column("reminders", "packing_list_id", new_column_name="list_id")

    # ---- Prices (Phase 6 item 5): nullable, Numeric(10,2) ----
    op.add_column(
        "list_items",
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("list_items", "price")
    op.alter_column("reminders", "list_id", new_column_name="packing_list_id")

    # Lossy by nature: the ten packing categories were collapsed into
    # "packing" on upgrade, so all we can restore is a valid value.
    op.execute("UPDATE lists SET kind = 'custom' WHERE kind NOT IN ('custom', 'packing')")
    op.execute("UPDATE lists SET kind = 'travel' WHERE kind = 'packing'")
    op.alter_column("lists", "kind", new_column_name="category")

    op.execute("ALTER INDEX ix_list_items_section_id RENAME TO ix_packing_items_section_id")
    op.execute("ALTER INDEX ix_list_sections_list_id RENAME TO ix_packing_sections_list_id")
    op.rename_table("list_items", "packing_items")
    op.rename_table("list_sections", "packing_sections")
    op.rename_table("lists", "packing_lists")
