"""Supply status changes (SPEC §6 Supplies).

Status is manual-only — the owner taps in_stock / low / out; nothing is
ever auto-decremented. The one piece of real logic lives here: when a
supply runs low/out it gets pushed into Enchanted Spoon's shopping list
exactly once per low-run, deduped via `last_pushed_at`:

- mark low/out  -> push to Enchanted Spoon if not already pushed this run,
                   stamp last_pushed_at on success
- mark in_stock -> clear last_pushed_at, so the NEXT time it runs low
                   it's pushed again
"""

from datetime import datetime, timezone

from app.models.supply import Supply
from app.services import mealgenie

STATUSES = ("in_stock", "low", "out")


def set_status(supply: Supply, status: str) -> bool:
    """Apply a manual status tap. Returns True if the supply was pushed to
    Enchanted Spoon's shopping list as a result. Caller commits."""
    supply.status = status

    if status == "in_stock":
        supply.last_pushed_at = None
        return False

    if supply.last_pushed_at is not None:
        return False  # already on the list this low-run

    if mealgenie.push_item(supply.name):
        supply.last_pushed_at = datetime.now(timezone.utc)
        return True
    return False
