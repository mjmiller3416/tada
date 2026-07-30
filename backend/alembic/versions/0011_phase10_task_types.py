"""phase 10: task types & scheduling lanes

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-30

Additive only (SPEC §8): one NOT NULL DEFAULT 'routine' column on tasks,
then two backfills in the same migration:

1. category='maintenance' -> task_type='maintenance'. task_type SUPERSEDES
   category from here on; the category column stays untouched purely for
   rollback safety (no code reads it anymore).
2. A name-based mapping for the seeded starter tasks (Tada is one
   household — a reviewed one-time mapping beats a clever inference
   engine). The names are the exact strings services/starter_tasks.py has
   seeded since Phase 1; matching is applied only to non-maintenance
   rows. Anything unmatched — including every task she made by hand —
   stays 'routine', the safe default that behaves exactly as today.
   Phase 11 gives her the review pass to correct types by hand.

The per-type counts are printed so the deploy log shows the split.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Exact seeded starter-task names -> lane, per the Phase 10 build prompt.
# routine is the default and deliberately absent: everything unlisted
# (including "Wipe the stovetop", "Clean the toilet", laundry loads, and
# all of her hand-made tasks) stays 'routine'.
NAME_TYPES: dict[str, str] = {
    # weekly_blessing — the recurring whole-home upkeep
    "Vacuum the floor": "weekly_blessing",
    "Vacuum the floor & rug": "weekly_blessing",
    "Vacuum or sweep": "weekly_blessing",
    "Vacuum or sweep the floor": "weekly_blessing",
    "Sweep or vacuum the floor": "weekly_blessing",
    "Mop the floor": "weekly_blessing",
    "Dust the surfaces": "weekly_blessing",
    "Dust the surfaces & shelves": "weekly_blessing",
    "Dust the desk & shelves": "weekly_blessing",
    "Dust ledges & frames": "weekly_blessing",
    "Change the sheets": "weekly_blessing",
    "Clean the mirror": "weekly_blessing",
    "Swap the towels": "weekly_blessing",
    # zone — the detail/declutter missions
    "Clean the microwave": "zone",
    "Wipe cabinet fronts & handles": "zone",
    "Clean out the fridge": "zone",
    "Deep-clean the oven": "zone",
    "Scrub the shower / tub": "zone",
    "Wash the bath mats": "zone",
    "Vacuum under the cushions": "zone",
    "Wash the windows": "zone",
    "Wipe the TV & electronics": "zone",
    "Polish the table & chairs": "zone",
    "Sort the paper pile": "zone",
    "Deep-clean the washer (empty hot run)": "zone",
    "Declutter one drawer or shelf": "zone",
    "Declutter outgrown toys": "zone",
    "Declutter one corner": "zone",
    "Declutter one shelf or bin": "zone",
    "Declutter one spot": "zone",
    "Tidy the workbench / shelves": "zone",
}


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "task_type",
            sa.String(length=30),
            nullable=False,
            server_default="routine",
        ),
    )

    bind = op.get_bind()
    tasks = sa.table(
        "tasks",
        sa.column("name", sa.String),
        sa.column("category", sa.String),
        sa.column("task_type", sa.String),
    )

    # Backfill 1: the old category is authoritative for maintenance.
    bind.execute(
        tasks.update()
        .where(tasks.c.category == "maintenance")
        .values(task_type="maintenance")
    )

    # Backfill 2: name-based typing for the seeded starter tasks — never
    # applied over a maintenance row.
    for name, task_type in NAME_TYPES.items():
        bind.execute(
            tasks.update()
            .where(tasks.c.name == name, tasks.c.category != "maintenance")
            .values(task_type=task_type)
        )

    # The split, for the deploy log — eyeball these before Phase 11.
    counts = bind.execute(
        sa.select(tasks.c.task_type, sa.func.count())
        .group_by(tasks.c.task_type)
        .order_by(tasks.c.task_type)
    ).all()
    print("Phase 10 task_type backfill:")
    for task_type, count in counts:
        print(f"  {task_type}: {count}")


def downgrade() -> None:
    op.drop_column("tasks", "task_type")
