"""Parent check: "ready to check", "checked" and "sent back".

A parent can turn on `needs_check` for a chore. From then on a kid's
Done doesn't just say "done": it says "done, ready for a parent to look".
A parent then either marks it **checked** (they physically inspected it
and it's good) or **sends it back** (not up to standard, optionally with
a note), which makes it due again.

Where the state lives: on the CompletionLog row. A check is a verdict on
one specific completion — the kid's claim and the parent's inspection
are the same event — so the row carries `check_status` ("ready" /
"checked" / "sent_back"), who checked it and when, and the note. The
task carries only the opt-in. "Waiting for a check" is therefore simply
"the task's latest completion is ready"; nothing on the task has to be
kept in sync.

The decay rule: decay resets at "ready to check", not at "checked". The
spec's first idea is that decay measures how long since the work was
actually done (SPEC §1, §4) — a chore cleaned on Sunday and inspected on
Tuesday was cleaned on Sunday. Waiting for "checked" would keep the chore
aging, and nagging the kid, for as long as the parent takes to look (the
opposite of "never guilt-inducing"), would push the next cycle later than
the real work, and would land a weekly chore finished on Sunday and
checked on Monday in the wrong week. "Checked" is a quality verdict that
changes nothing about the schedule. A send-back reverses the reset
exactly as undo does (restoring `previous_last_done_at`), so a chore that
wasn't really done is due again with its true history.

Who can do what: anyone who may complete a chore may mark it ready
(services/completion.can_complete). Only adults (role "owner") may mark
checked, send back, or undo a check — the routes use require_owner and
this module checks again.
"""

from datetime import datetime, timezone, tzinfo
from typing import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.completion_log import CompletionLog
from app.models.task import Task
from app.models.user import User
from app.services import scheduling

READY = "ready"
CHECKED = "checked"
SENT_BACK = "sent_back"

#: Longest note a parent can send back with a chore.
NOTE_MAX_LENGTH = 500


class CheckRefused(Exception):
    """The move doesn't fit the completion's state (409). The message is
    a plain sentence for the person or the model."""


class NotAParent(Exception):
    """Only an adult may check, send back or undo a check (403)."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def counts_as_done():
    """SQL filter: completions that count as done. A sent-back completion
    was judged not done, so done-today lists, the Hearth wall and Orbit's
    recaps leave it out."""
    return or_(
        CompletionLog.check_status.is_(None),
        CompletionLog.check_status != SENT_BACK,
    )


def wants_check(task: Task, user: User) -> bool:
    """Whether a plain Done by `user` should become "ready to check": the
    task opted in and the person doing it is a kid. An adult's own Done
    stays an ordinary completion — an adult doing or confirming the job
    is the check."""
    return bool(task.needs_check) and user.role == "kid"


def _require_parent(user: User) -> None:
    if user.role != "owner":
        raise NotAParent("Only a parent can do that.")


def pending_states(
    db: Session, task_ids: Iterable[int] | None = None
) -> dict[int, CompletionLog]:
    """Per task, the latest completion when it is "ready" or "sent_back".

    "Latest" is the same rule undo uses (completed_at, ties by id): a
    ready completion superseded by a newer one (a parent did it again
    themselves, say) is no longer waiting, and a sent-back one stops
    showing "sent back" once the chore has been done again."""
    query = (
        select(CompletionLog)
        .where(CompletionLog.check_status.in_((READY, SENT_BACK)))
        .order_by(CompletionLog.completed_at.desc(), CompletionLog.id.desc())
    )
    if task_ids is not None:
        ids = list(task_ids)
        if not ids:
            return {}
        query = query.where(CompletionLog.task_id.in_(ids))
    states: dict[int, CompletionLog] = {}
    seen: set[int] = set()
    for log in db.scalars(query).all():
        if log.task_id in seen:
            continue  # only the newest flagged row per task can be current
        seen.add(log.task_id)
        if not scheduling.has_newer_completion(db, log):
            states[log.task_id] = log
    return states


def waiting_for_check(db: Session) -> list[CompletionLog]:
    """The parents' "To check" list: every active task whose latest
    completion is waiting for a check, longest-waiting first. Task, room
    and the member who did it ride along for the projection."""
    states = pending_states(db)
    ready_ids = [log.id for log in states.values() if log.check_status == READY]
    if not ready_ids:
        return []
    return list(
        db.scalars(
            select(CompletionLog)
            .join(Task, CompletionLog.task_id == Task.id)
            .options(joinedload(CompletionLog.task).joinedload(Task.room))
            .where(CompletionLog.id.in_(ready_ids), Task.is_active.is_(True))
            .order_by(CompletionLog.completed_at, CompletionLog.id)
        ).all()
    )


def pending_ready(db: Session, task: Task) -> CompletionLog | None:
    """The task's completion that is already waiting for a check, if any —
    so a second "ready" for the same work doesn't stack a new row whose
    send-back would restore the first, unchecked claim as if it were
    real history."""
    log = pending_states(db, [task.id]).get(task.id)
    return log if log is not None and log.check_status == READY else None


def mark_checked(
    db: Session, log: CompletionLog, parent: User, now: datetime | None = None
) -> CompletionLog:
    """A parent physically inspected the chore and approves it. Changes no
    decay state (the reset happened at "ready"). Marking an already
    checked completion again is a no-op. Caller commits."""
    _require_parent(parent)
    if log.check_status == CHECKED:
        return log
    if log.check_status == SENT_BACK:
        raise CheckRefused(
            "That one was sent back, so it needs doing again before it can be checked."
        )
    if log.check_status != READY:
        raise CheckRefused("That completion isn't waiting for a check.")
    log.check_status = CHECKED
    log.checked_by = parent.id
    log.checked_at = now or _utcnow()
    log.check_note = None
    db.flush()
    return log


def send_back(
    db: Session,
    log: CompletionLog,
    parent: User,
    note: str | None = None,
    now: datetime | None = None,
    tz: tzinfo | None = None,
) -> CompletionLog:
    """Not up to standard: the chore is due again. Reverses the decay
    reset exactly as undo does (last_done_at goes back to what the
    completion overwrote) and the campaign tick it made, but keeps the
    row, marked sent back with the parent, the time and the note, so the
    kid sees why. Streaks and badges are left alone, as undo leaves them.
    Refused when a newer completion of the task stands, since rewinding
    past it would erase real work. Caller commits."""
    from app.services import campaigns as campaign_service

    _require_parent(parent)
    if log.check_status == CHECKED:
        raise CheckRefused(
            "That one's already been checked. Undo the check first if it needs another go."
        )
    if log.check_status == SENT_BACK:
        raise CheckRefused("That one has already been sent back.")
    if log.check_status != READY:
        raise CheckRefused("That completion isn't waiting for a check.")
    if scheduling.has_newer_completion(db, log):
        raise CheckRefused(
            "This chore was done again since, so there's nothing to send back."
        )
    task = db.get(Task, log.task_id)
    task.last_done_at = log.previous_last_done_at
    campaign_service.untick_for_undone_completion(db, log, tz or timezone.utc)
    log.check_status = SENT_BACK
    log.checked_by = parent.id
    log.checked_at = now or _utcnow()
    cleaned = (note or "").strip()
    log.check_note = cleaned[:NOTE_MAX_LENGTH] or None
    db.flush()
    return log


def undo_check(
    db: Session,
    log: CompletionLog,
    parent: User,
    tz: tzinfo | None = None,
) -> CompletionLog:
    """Take back a parent's verdict: a checked or sent-back completion goes
    back to "ready to check". Undoing a send-back re-applies the decay
    reset (and the campaign tick) the send-back reversed — refused if the
    chore has been done again since, because that newer completion now
    owns the decay state. Caller commits."""
    from app.services import campaigns as campaign_service

    _require_parent(parent)
    if log.check_status == SENT_BACK:
        if scheduling.has_newer_completion(db, log):
            raise CheckRefused(
                "This chore was done again since, so the send-back can't be undone."
            )
        task = db.get(Task, log.task_id)
        task.last_done_at = log.completed_at
        completed_at = log.completed_at
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=timezone.utc)
        campaign_service.mark_done_in_running_campaigns(
            db, task.id, completed_at.astimezone(tz or timezone.utc).date()
        )
    elif log.check_status != CHECKED:
        raise CheckRefused("There's no check on that completion to undo.")
    log.check_status = READY
    log.checked_by = None
    log.checked_at = None
    log.check_note = None
    db.flush()
    return log
