"""Read compositions for the Hearth wall (docs/hearth-integration.md).

Hearth's two aggregate reads — a member's done-today feed and every kid's
chore board — aren't new data, just new lenses over the same CompletionLog
and the same decay-ranked chores the app already serves. Everything here
composes existing pieces (scheduling.chores_for_user, the CompletionLog
day window) rather than adding a parallel chore system.
"""

from datetime import datetime, time, timedelta, tzinfo

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.completion_log import CompletionLog
from app.models.task import Task
from app.models.user import User
from app.services import scheduling


def _local_day_bounds(tz: tzinfo) -> tuple[datetime, datetime]:
    """The [start, end) of today in the given timezone — her calendar day,
    not UTC's (same boundary routers/done_today.py uses)."""
    local_today = datetime.now(tz).date()
    day_start = datetime.combine(local_today, time.min, tzinfo=tz)
    return day_start, day_start + timedelta(days=1)


def member_completions_today(
    db: Session, member_id: int, tz: tzinfo
) -> list[CompletionLog]:
    """One member's completions from today, newest first — the done-today
    celebration feed for the Hearth Clean view. Task + room eager-loaded
    for the projection."""
    day_start, day_end = _local_day_bounds(tz)
    return list(
        db.scalars(
            select(CompletionLog)
            .options(joinedload(CompletionLog.task).joinedload(Task.room))
            .where(
                CompletionLog.completed_by == member_id,
                CompletionLog.completed_at >= day_start,
                CompletionLog.completed_at < day_end,
            )
            .order_by(CompletionLog.completed_at.desc())
        ).all()
    )


def kids_chores(
    db: Session, tz: tzinfo
) -> list[tuple[User, list[dict]]]:
    """Every kid's chore board for today: for each `role=="kid"` member,
    their outstanding chores plus what they've already checked off (gap
    #6 — outstanding + completed).

    Outstanding is `scheduling.chores_for_user(...).mine` — active chores
    assigned to that kid, decay-ranked and already past the shared
    freshness gate (a chore done today drops out until it needs doing
    again). Completed is today's CompletionLog for that kid.

    Deduped by task, completed winning: a daily chore checked off this
    morning can re-age past the freshness gate by evening and reappear in
    `mine`, but "you did it today" is the honest thing to show, so it is
    listed once, done. Each entry is {task, done, completion_id}; the
    completion_id is the undo handle for a done chore, None otherwise."""
    day_start, day_end = _local_day_bounds(tz)
    kids = db.scalars(
        select(User).where(User.role == "kid").order_by(User.id)
    ).all()

    boards: list[tuple[User, list[dict]]] = []
    for kid in kids:
        logs = db.scalars(
            select(CompletionLog)
            .options(joinedload(CompletionLog.task).joinedload(Task.room))
            .where(
                CompletionLog.completed_by == kid.id,
                CompletionLog.completed_at >= day_start,
                CompletionLog.completed_at < day_end,
            )
            .order_by(CompletionLog.completed_at.desc())
        ).all()
        # Most recent completion per task (desc order → first seen wins), so
        # a chore done twice today shows once with its latest undo handle.
        done_by_task: dict[int, CompletionLog] = {}
        for log in logs:
            done_by_task.setdefault(log.task_id, log)

        mine, _ = scheduling.chores_for_user(db, kid.id, tz=tz)
        entries: list[dict] = [
            {"task": task, "done": False, "completion_id": None}
            for task in mine
            if task.id not in done_by_task  # completed today wins
        ]
        entries += [
            {"task": log.task, "done": True, "completion_id": log.id}
            for log in done_by_task.values()
        ]
        boards.append((kid, entries))
    return boards
