"""Read compositions for the Orbit integration (routers/orbit.py).

Orbit is Link's personal planner, a separate app. It needs a member's
chore board (today / upcoming / recurring), their completion history and
a few accumulation-only stats. None of that is new data: it's the same
decay-ranked chores the kid surface serves (scheduling.chores_for_user),
the same CompletionLog, and the same streak columns the completion path
maintains. This module composes those pieces; it adds no scheduling rule
of its own. Kept apart from services/hearth.py on purpose: the two
integrations evolve (and can be switched off) independently.

Every "day" here is the HOUSEHOLD's day, i.e. the primary owner's
timezone, the clock zone weeks and Hearth's chore board already use.
Query bounds are converted to UTC before they hit the database so the
comparison is exact on Postgres (timestamptz) and SQLite (naive UTC).
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.completion_log import CompletionLog
from app.models.task import Task
from app.models.user import User
from app.services import scheduling, settings_service

#: How far ahead "upcoming" looks, in days after today.
UPCOMING_DAYS = 7

#: The longest completions window Orbit may ask for in one call.
MAX_HISTORY_DAYS = 92

#: Friendly names for the SPEC §3 cadence tier presets that aren't a
#: whole number of weeks in everyday speech.
_TIER_LABELS = {1: "every day", 7: "every week", 30: "every month", 91: "every 3 months", 365: "every year"}


@dataclass
class ChoreEntry:
    """One chore on a member's board, with everything the router needs to
    project it: today's completion by this member (if any) and when the
    chore is next due on the chore surface."""

    task: Task
    done: bool
    log: CompletionLog | None
    due_on: date | None
    can_undo: bool


@dataclass
class MemberBoard:
    today: date
    tz: tzinfo
    today_entries: list[ChoreEntry]
    upcoming: list[ChoreEntry]
    recurring: list[ChoreEntry]
    completed_today: int
    completed_this_week: int


# ---------------------------------------------------------------------------
# Clock helpers
# ---------------------------------------------------------------------------

def household_timezone(db: Session) -> tzinfo:
    """The household's clock: the primary owner's timezone setting (the
    same clock Hearth's /kids board and the zone weeks use). UTC only if
    there is somehow no owner."""
    owner = db.scalar(select(User).where(User.role == "owner").order_by(User.id))
    return settings_service.user_timezone(db, owner.id) if owner else timezone.utc


def timezone_name(tz: tzinfo) -> str:
    """The IANA name for a resolved timezone ("UTC" for the fallback)."""
    return getattr(tz, "key", None) or "UTC"


def day_start_utc(day: date, tz: tzinfo) -> datetime:
    """Local midnight starting `day` in `tz`, as a UTC instant."""
    return datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc)


def localize(dt: datetime, tz: tzinfo) -> datetime:
    """A stored timestamp (aware UTC on Postgres, naive UTC on SQLite)
    rendered in `tz`, so the ISO string carries the household offset."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz)


def cadence_label(cadence_days: int | None) -> str | None:
    """Plain words for a cadence: "every day", "every week", "every 2
    weeks", "every 3 days"; the monthly/seasonal/annual tiers by name."""
    if cadence_days is None or cadence_days <= 0:
        return None
    if cadence_days in _TIER_LABELS:
        return _TIER_LABELS[cadence_days]
    if cadence_days % 7 == 0:
        return f"every {cadence_days // 7} weeks"
    return f"every {cadence_days} days"


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def _member_logs(
    db: Session, member_id: int, start: datetime, end: datetime
) -> list[CompletionLog]:
    """A member's completions in [start, end) (UTC instants), newest
    first, task + room eager-loaded for projection."""
    return list(
        db.scalars(
            select(CompletionLog)
            .options(joinedload(CompletionLog.task).joinedload(Task.room))
            .where(
                CompletionLog.completed_by == member_id,
                CompletionLog.completed_at >= start,
                CompletionLog.completed_at < end,
            )
            .order_by(CompletionLog.completed_at.desc(), CompletionLog.id.desc())
        ).all()
    )


def member_completions(
    db: Session, member_id: int, start: date, end: date, tz: tzinfo
) -> list[CompletionLog]:
    """A member's completions on local days start..end inclusive, newest
    first, every source (Orbit's recaps count all of Link's work, not
    just what he ticked in Orbit)."""
    return _member_logs(
        db, member_id, day_start_utc(start, tz), day_start_utc(end + timedelta(days=1), tz)
    )


def _member_pool(db: Session, member_id: int) -> list[Task]:
    """Every active chore this member can do: assigned to them, or
    unassigned and left open to claim. Projects are never claimable
    automatically (scheduling.chores_for_user, issue #22) — only an
    assigned project is theirs."""
    return list(
        db.scalars(
            select(Task)
            .options(joinedload(Task.room))
            .where(
                Task.is_active.is_(True),
                or_(
                    Task.assignee_id == member_id,
                    (Task.assignee_id.is_(None))
                    & (Task.claimable.is_(True))
                    & (Task.task_type != "project"),
                ),
            )
            .order_by(Task.id)
        ).unique().all()
    )


def _can_undo(db: Session, log: CompletionLog, member: User, now: datetime) -> bool:
    """Would POST /undo succeed for this completion right now? The same
    checks the undo path runs: the member owns it (or is an owner), and
    scheduling.check_undoable passes in the member's own timezone, the
    clock routers/orbit.py hands undo_completion (as Hearth does)."""
    if member.role != "owner" and log.completed_by != member.id:
        return False
    try:
        scheduling.check_undoable(
            db, log, now=now, tz=settings_service.user_timezone(db, member.id)
        )
    except (scheduling.UndoWindowClosed, scheduling.UndoNotLatest):
        return False
    return True


def member_board(
    db: Session, member: User, tz: tzinfo, now: datetime | None = None
) -> MemberBoard:
    """A member's chore board for Orbit.

    - today: what the kid surface shows them right now (chores_for_user:
      their own chores, then up-for-grabs, each decay-ranked) plus every
      chore they completed today. Deduped by task with completed winning,
      exactly like Hearth's /kids board: a daily chore done this morning
      can re-age past the freshness gate by evening, but "you did it
      today" is the honest thing to show.
    - upcoming: chores from their pool that are not on today's board but
      will be within UPCOMING_DAYS, by scheduling.chore_due_at.
    - recurring: the whole pool except projects (manual-only, not
      recurring), with next due date and today's done state.
    """
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(tz).date()
    day_start = day_start_utc(today, tz)
    week_start = day_start_utc(today - timedelta(days=today.weekday()), tz)

    today_logs = _member_logs(db, member.id, day_start, day_start_utc(today + timedelta(days=1), tz))
    done_by_task: dict[int, CompletionLog] = {}
    for log in today_logs:  # newest first, so the latest completion wins
        done_by_task.setdefault(log.task_id, log)

    def due_on(task: Task) -> date:
        """Next due date on the chore surface, never earlier than today."""
        return max(today, scheduling.chore_due_at(task, now, tz).astimezone(tz).date())

    def entry(task: Task, due: date | None) -> ChoreEntry:
        log = done_by_task.get(task.id)
        return ChoreEntry(
            task=task,
            done=log is not None,
            log=log,
            due_on=due,
            can_undo=log is not None and _can_undo(db, log, member, now),
        )

    mine, up_for_grabs = scheduling.chores_for_user(db, member.id, now=now, tz=tz)
    today_entries = [entry(t, today) for t in [*mine, *up_for_grabs] if t.id not in done_by_task]
    today_entries += [entry(log.task, today) for log in done_by_task.values()]
    on_today = {e.task.id for e in today_entries}

    pool = _member_pool(db, member.id)
    horizon = today + timedelta(days=UPCOMING_DAYS)
    upcoming = []
    for task in pool:
        if task.id in on_today:
            continue
        due = due_on(task)
        if today < due <= horizon:
            upcoming.append(entry(task, due))
    upcoming.sort(key=lambda e: (e.due_on, e.task.name.lower(), e.task.id))

    recurring = [entry(t, due_on(t)) for t in pool if t.task_type != "project"]
    recurring.sort(key=lambda e: (e.task.cadence_days, e.task.name.lower(), e.task.id))

    completed_this_week = db.scalar(
        select(func.count(CompletionLog.id)).where(
            CompletionLog.completed_by == member.id,
            CompletionLog.completed_at >= week_start,
        )
    )
    return MemberBoard(
        today=today,
        tz=tz,
        today_entries=today_entries,
        upcoming=upcoming,
        recurring=recurring,
        completed_today=len(today_logs),
        completed_this_week=completed_this_week or 0,
    )
