"""The one completion path (SPEC §8: "every completion path counts
exactly once").

Completing a task is never just resetting the decay curve — a running
campaign gets its tick, a pending snooze reminder is dropped, and a kid's
completion brags to the owner. Those side-effects used to live inline in
routers/tasks.py; they now live here so the home screen, focus sessions,
kid chores, and the Hearth wall (docs/hearth-integration.md) all complete
tasks identically. The pure decay reset stays in services/scheduling.py —
this module orchestrates the surrounding effects around it.
"""

import logging

from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.user import User
from app.services import campaigns as campaign_service
from app.services import reminder_service, scheduling
from app.services import zones as zone_service
from app.services.push_service import notify_owners

logger = logging.getLogger(__name__)


def can_complete(task: Task, user: User) -> bool:
    """The owner can complete anything. A kid can check off their own
    chores, or an unassigned one that was left open to claim (SPEC §6:
    'see their assigned/claimable chores and check them off')."""
    if user.role == "owner":
        return True
    if task.assignee_id == user.id:
        return True
    return task.claimable and task.assignee_id is None


def record_completion(db: Session, task: Task, user: User, source: str) -> int:
    """Complete `task` as `user`: tick any running campaign that lists it,
    reset the decay curve + advance streaks/badges (scheduling.complete_task),
    and drop any pending snooze reminder so finished work never nudges.
    Returns the new CompletionLog id — read here, pre-commit, because the
    ORM object expires once the CALLER commits (which it must)."""
    # Marked BEFORE complete_task so the Phase 5 badge check inside it sees
    # a campaign this very completion just finished (progress is progress —
    # SPEC §6, Phase 3).
    campaign_service.mark_done_in_running_campaigns(
        db, task.id, zone_service.local_today(db, user.id)
    )
    log = scheduling.complete_task(db, task, user, source)
    completion_id = log.id
    reminder_service.clear_task_reminders(db, task.id)
    return completion_id


def notify_owner_if_kid(
    db: Session, user: User, task: Task, completion_id: int
) -> None:
    """A kid's completion brags to the owner (SPEC §6) — positive-only
    copy, never an audit. Call AFTER the completion is committed and
    shield it: a push-layer failure must never turn an already-durable
    completion into a 500 that makes the kid retap and double-log (issue
    #24). A no-op for the owner's own completions."""
    if user.role != "kid":
        return
    try:
        first_name = user.name.split()[0]
        where = f" in the {task.room.name.lower()}" if task.room else ""
        notify_owners(db, "Ta-da! 🎉", f"{first_name} just checked off {task.name}{where}.")
    except Exception:
        logger.exception("Owner notification failed after completion %d", completion_id)
        db.rollback()  # leave the session usable for anything the caller does next
