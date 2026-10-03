"""The Orbit integration API.

Orbit is Link's personal planner, a separate app. It reads his chores
from Tada and checks them off (and undoes a mis-tap), with every
completion landing in Tada exactly as if he'd tapped it here. It calls
Tada server-to-server with one static APP token (not a user session) and
names the acting household member in each request, the same shape as the
Hearth wall's router but a fully separate surface: its own token, its own
prefix, its own shapes, so either integration can change or be switched
off without touching the other.

Scope is deliberately narrow: reads (members, a member's chore board,
their completion history) plus complete and undo. No task, settings or
reward-state writes beyond what a normal completion already does.

Every id on the wire is a string (see schemas/orbit.py). The whole router
is gated on ORBIT_API_TOKEN: unset means the integration is off and every
route returns 503, the config-only rollback boundary.
"""

import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.models.completion_log import CompletionLog
from app.models.task import Task
from app.models.user import User
from app.schemas.orbit import (
    OrbitChore,
    OrbitChoresResponse,
    OrbitCompleteRequest,
    OrbitCompleteResponse,
    OrbitCompletion,
    OrbitCompletionsResponse,
    OrbitMember,
    OrbitMemberRef,
    OrbitMembersResponse,
    OrbitStats,
    OrbitUndoRequest,
)
from app.services import auth_service, completion, scheduling, settings_service
from app.services import orbit as orbit_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orbit", tags=["orbit"])

#: The source stamped on every completion made through Orbit.
ORBIT_SOURCE = "orbit"


def require_orbit_app(authorization: str | None = Header(default=None)) -> None:
    """Authorize the APP, not a user: a constant-time check of the
    `Authorization: Bearer <token>` header against ORBIT_API_TOKEN. With
    no token configured the integration is off: 503, so an unconfigured
    backend is never merely unlocked by omitting the header."""
    if not settings.orbit_api_token:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Orbit integration is not configured"
        )
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Missing API token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    presented = authorization[len("Bearer ") :].strip()
    if not auth_service.verify_orbit_token(presented):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_or_404(db: Session, model, raw: str, label: str):
    """Look up a row by a string id. Anything that isn't a Tada integer id
    can't name a real row, so it's a 404 like any other unknown id."""
    try:
        row_id = int(raw)
    except (TypeError, ValueError):
        row_id = None
    row = db.get(model, row_id) if row_id is not None else None
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found")
    return row


def _get_task(db: Session, raw: str) -> Task:
    task = _get_or_404(db, Task, raw, "Task")
    # Room eager-loaded for the owner notification copy.
    return db.scalar(select(Task).options(joinedload(Task.room)).where(Task.id == task.id))


def _first_name(user: User) -> str:
    return (user.name.split() or ["That member"])[0]


def _chore(entry: orbit_service.ChoreEntry, member: User, tz) -> OrbitChore:
    task = entry.task
    return OrbitChore(
        id=str(task.id),
        name=task.name,
        room=task.room.name if task.room else None,
        instructions=task.notes or None,
        estimated_minutes=task.estimated_minutes,
        effort=task.effort,
        cadence_days=task.cadence_days,
        cadence_label=orbit_service.cadence_label(task.cadence_days),
        preferred_day=task.preferred_day,
        due_on=entry.due_on,
        done=entry.done,
        completion_id=str(entry.log.id) if entry.log else None,
        completed_at=orbit_service.localize(entry.log.completed_at, tz) if entry.log else None,
        can_undo=entry.can_undo,
        claimable=task.assignee_id is None and task.claimable,
        assigned_to_member=task.assignee_id == member.id,
    )


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

@router.get("/members", response_model=OrbitMembersResponse)
def list_members(
    _: None = Depends(require_orbit_app), db: Session = Depends(get_db)
) -> OrbitMembersResponse:
    """Every household account (owner first, then kids, by id) so Orbit
    can pick its member. Tada has no deactivated-member state, so every
    account is active. Names and roles only; never a PIN or email."""
    users = db.scalars(select(User).order_by(User.role.desc(), User.id)).all()
    return OrbitMembersResponse(
        members=[OrbitMember(id=str(u.id), name=u.name, role=u.role) for u in users]
    )


@router.get("/chores", response_model=OrbitChoresResponse)
def chores(
    member: str,
    _: None = Depends(require_orbit_app),
    db: Session = Depends(get_db),
) -> OrbitChoresResponse:
    """A member's chore board: today (outstanding + done today), upcoming
    (due within a week), recurring (everything with a cadence), and
    accumulation-only stats. See services/orbit.member_board."""
    acting: User = _get_or_404(db, User, member, "Member")
    tz = orbit_service.household_timezone(db)
    board = orbit_service.member_board(db, acting, tz)
    return OrbitChoresResponse(
        member=OrbitMemberRef(id=str(acting.id), name=acting.name),
        date=board.today,
        timezone=orbit_service.timezone_name(tz),
        today=[_chore(e, acting, tz) for e in board.today_entries],
        upcoming=[_chore(e, acting, tz) for e in board.upcoming],
        recurring=[_chore(e, acting, tz) for e in board.recurring],
        stats=OrbitStats(
            current_streak=acting.current_streak,
            longest_streak=acting.longest_streak,
            completed_today=board.completed_today,
            completed_this_week=board.completed_this_week,
        ),
    )


@router.get("/completions", response_model=OrbitCompletionsResponse)
def completions(
    member: str,
    start: date | None = None,
    end: date | None = None,
    _: None = Depends(require_orbit_app),
    db: Session = Depends(get_db),
) -> OrbitCompletionsResponse:
    """A member's completions on household-local days start..end
    (inclusive), newest first, every source. Both default sensibly when
    omitted (end = today, start = six days before end); a window longer
    than 92 days, or an end before its start, is 422."""
    acting: User = _get_or_404(db, User, member, "Member")
    tz = orbit_service.household_timezone(db)
    end = end or datetime.now(tz).date()
    start = start or end - timedelta(days=6)
    if end < start:
        raise HTTPException(
            422, "end must be on or after start"
        )
    if (end - start).days + 1 > orbit_service.MAX_HISTORY_DAYS:
        raise HTTPException(
            422,
            f"That range is too long; ask for {orbit_service.MAX_HISTORY_DAYS} days or fewer",
        )
    logs = orbit_service.member_completions(db, acting.id, start, end, tz)
    return OrbitCompletionsResponse(
        completions=[
            OrbitCompletion(
                completion_id=str(log.id),
                task_id=str(log.task_id),
                task_name=log.task.name,
                room=log.task.room.name if log.task.room else None,
                completed_at=orbit_service.localize(log.completed_at, tz),
                source=log.source,
            )
            for log in logs
        ]
    )


# ---------------------------------------------------------------------------
# Writes (the only two the Orbit token is scoped to)
# ---------------------------------------------------------------------------

@router.post("/complete", response_model=OrbitCompleteResponse)
def complete(
    req: OrbitCompleteRequest,
    _: None = Depends(require_orbit_app),
    db: Session = Depends(get_db),
) -> OrbitCompleteResponse:
    """Complete a task AS `member_id`, stamped source "orbit". Runs the
    one shared completion path (services/completion.py), the same one the
    app and the Hearth wall use, so decay, streaks, badges, campaign ticks
    and the owner's "Ta-da!" push all happen exactly once, exactly as for
    any other completion. Returns the completion id for undo."""
    member: User = _get_or_404(db, User, req.member_id, "Member")
    task = _get_task(db, req.task_id)
    if not completion.can_complete(task, member):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"{_first_name(member)} can't check that one off. It's someone "
            "else's chore and isn't up for grabs.",
        )
    completion_id = completion.record_completion(db, task, member, ORBIT_SOURCE)
    db.commit()
    logger.info(
        "Orbit completion %d: task %d by member %d", completion_id, task.id, member.id
    )
    completion.notify_owner_if_kid(db, member, task, completion_id)
    log = db.get(CompletionLog, completion_id)
    return OrbitCompleteResponse(
        completion_id=str(completion_id),
        completed_at=orbit_service.localize(
            log.completed_at, orbit_service.household_timezone(db)
        ),
    )


@router.post("/undo", status_code=status.HTTP_204_NO_CONTENT)
def undo(
    req: OrbitUndoRequest,
    _: None = Depends(require_orbit_app),
    db: Session = Depends(get_db),
) -> None:
    """Reverse one of today's completions (scheduling.undo_completion:
    decay state only, never streaks or badges), with the same rules as
    the app and Hearth: an owner may undo any completion, a member only
    their own; only today's (in the member's timezone) and only the
    task's latest, else 409 with a friendly reason."""
    member: User = _get_or_404(db, User, req.member_id, "Member")
    log: CompletionLog = _get_or_404(db, CompletionLog, req.completion_id, "Completion")
    if member.role != "owner" and log.completed_by != member.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"That one was checked off by someone else, so {_first_name(member)} can't undo it.",
        )
    completion_id = log.id
    try:
        scheduling.undo_completion(
            db, log, tz=settings_service.user_timezone(db, member.id)
        )
    except (scheduling.UndoWindowClosed, scheduling.UndoNotLatest) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    db.commit()
    logger.info("Orbit undo of completion %d by member %d", completion_id, member.id)
