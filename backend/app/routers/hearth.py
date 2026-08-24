"""The device-scoped Hearth API (docs/hearth-integration.md).

Hearth's wall shows the household's Clean and Chores views. It calls Tada
server-to-server with a single static DEVICE token (not a user session),
and names the acting household member in each request. This router is that
contract: a small set of reads plus complete/undo, composed entirely from
existing services — no new scheduling rules, no writes beyond a completion
and its undo (the token is deliberately scoped no wider, per the doc).

Every id on the wire is a string (see schemas/hearth.py). The whole router
is gated on HEARTH_DEVICE_TOKEN: unset means the integration is off and
every route returns 503 — the permanent, config-only rollback boundary.
"""

from datetime import timezone, tzinfo

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.models.completion_log import CompletionLog
from app.models.room import Room
from app.models.task import Task
from app.models.user import User
from app.schemas.hearth import (
    HearthCompleteRequest,
    HearthCompleteResponse,
    HearthCompletion,
    HearthDoneTodayResponse,
    HearthKid,
    HearthKidChore,
    HearthKidsResponse,
    HearthNextResponse,
    HearthRoom,
    HearthRoomsResponse,
    HearthTask,
    HearthUndoRequest,
)
from app.services import auth_service, completion, scheduling, settings_service
from app.services import hearth as hearth_service

router = APIRouter(prefix="/api/hearth", tags=["hearth"])


def require_hearth_device(authorization: str | None = Header(default=None)) -> None:
    """Authorize the DEVICE, not a user (gap #1): a constant-time check of
    the `Authorization: Bearer <token>` header against HEARTH_DEVICE_TOKEN.
    With no token configured the integration is off — 503, so an
    unconfigured backend is never merely unlocked by omitting the header."""
    if not settings.hearth_device_token:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Hearth integration is not configured"
        )
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Missing device token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    presented = authorization[len("Bearer ") :].strip()
    if not auth_service.verify_device_token(presented):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid device token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_int_id(raw: str, label: str) -> int:
    """Every id arrives as a string (the contract stringifies them); turn
    one back into a Tada integer id or 400."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid {label}")


def _resolve_member(db: Session, raw: str) -> User:
    """The acting household member named by `memberId`. Hearth rejects
    anything off its own allowlist first; Tada still only honors a member
    that actually exists here."""
    member = db.get(User, _parse_int_id(raw, "memberId"))
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    return member


def _get_task(db: Session, task_id: int) -> Task:
    task = db.scalar(
        select(Task).options(joinedload(Task.room)).where(Task.id == task_id)
    )
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return task


def _localize(dt, tz: tzinfo):
    """A stored completion time (tz-aware UTC on Postgres, naive UTC on
    SQLite) rendered in the member's zone, so the serialized ISO string
    carries her local offset (the doc's `-04:00`)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz)


def _household_tz(db: Session) -> tzinfo:
    """The household's clock for the whole-board /kids read, which has no
    single acting member — the primary owner's timezone, the same clock
    zone weeks derive from. UTC only if there's somehow no owner."""
    owner = db.scalar(select(User).where(User.role == "owner").order_by(User.id))
    return settings_service.user_timezone(db, owner.id) if owner else timezone.utc


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

@router.get("/rooms", response_model=HearthRoomsResponse)
def list_rooms(
    _: None = Depends(require_hearth_device), db: Session = Depends(get_db)
) -> HearthRoomsResponse:
    """Rooms a Clean session can be scoped to — GET /api/rooms projected to
    id/name (gap #4). The id is opaque to Hearth; it round-trips to
    /next?room=."""
    rooms = db.scalars(select(Room).order_by(Room.sort_order, Room.id)).all()
    return HearthRoomsResponse(
        rooms=[HearthRoom(id=str(room.id), name=room.name) for room in rooms]
    )


@router.get("/next", response_model=HearthNextResponse)
def next_task(
    member: str,
    room: str | None = None,
    _: None = Depends(require_hearth_device),
    db: Session = Depends(get_db),
) -> HearthNextResponse:
    """The single highest-decay task for the scope (gap #4), or null — the
    calm rest state — when nothing is due. `member` is the acting adult;
    `room` (optional) scopes to a room. Returns id/name/room only; the
    decay score never crosses the wire (SPEC D4)."""
    acting = _resolve_member(db, member)
    room_id = _parse_int_id(room, "room") if room is not None else None
    task = scheduling.next_task_for_scope(
        db,
        for_user_id=acting.id,
        room_id=room_id,
        tz=settings_service.user_timezone(db, acting.id),
    )
    if task is None:
        return HearthNextResponse(task=None)
    return HearthNextResponse(
        task=HearthTask(
            id=str(task.id),
            name=task.name,
            room=task.room.name if task.room else None,
        )
    )


@router.get("/done-today", response_model=HearthDoneTodayResponse)
def done_today(
    member: str,
    _: None = Depends(require_hearth_device),
    db: Session = Depends(get_db),
) -> HearthDoneTodayResponse:
    """That member's completions today (gap #5), for the done-today
    celebration — server-filtered so the payload is honest to one member."""
    acting = _resolve_member(db, member)
    tz = settings_service.user_timezone(db, acting.id)
    logs = hearth_service.member_completions_today(db, acting.id, tz)
    return HearthDoneTodayResponse(
        completions=[
            HearthCompletion(
                completionId=str(log.id),
                taskName=log.task.name,
                room=log.task.room.name if log.task.room else None,
                completedAt=_localize(log.completed_at, tz),
            )
            for log in logs
        ]
    )


@router.get("/kids", response_model=HearthKidsResponse)
def kids(
    _: None = Depends(require_hearth_device), db: Session = Depends(get_db)
) -> HearthKidsResponse:
    """Every kid's outstanding + completed chores for today, keyed by Tada
    member id (gap #6). Hearth pairs these with its configured kids, so a
    kid with no chores simply isn't returned."""
    tz = _household_tz(db)
    return HearthKidsResponse(
        kids=[
            HearthKid(
                memberId=str(kid.id),
                chores=[
                    HearthKidChore(
                        id=str(entry["task"].id),
                        name=entry["task"].name,
                        done=entry["done"],
                        completionId=(
                            str(entry["completion_id"])
                            if entry["completion_id"] is not None
                            else None
                        ),
                    )
                    for entry in entries
                ],
            )
            for kid, entries in hearth_service.kids_chores(db, tz)
        ]
    )


# ---------------------------------------------------------------------------
# Writes (the only two the device token is scoped to)
# ---------------------------------------------------------------------------

@router.post("/complete", response_model=HearthCompleteResponse)
def complete(
    req: HearthCompleteRequest,
    _: None = Depends(require_hearth_device),
    db: Session = Depends(get_db),
) -> HearthCompleteResponse:
    """Complete a task AS `memberId`, stamped source "hearth" (gaps #2/#3).
    Runs the one shared completion path (services/completion.py), so a
    kid's tap on the wall notifies the owner exactly as their own device
    would. Returns the completion id so the wall can undo a mis-tap."""
    member = _resolve_member(db, req.memberId)
    task = _get_task(db, _parse_int_id(req.taskId, "taskId"))
    if not completion.can_complete(task, member):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "That member can't check off that task"
        )
    completion_id = completion.record_completion(db, task, member, req.source)
    db.commit()
    completion.notify_owner_if_kid(db, member, task, completion_id)
    return HearthCompleteResponse(completionId=str(completion_id))


@router.post("/undo", status_code=status.HTTP_204_NO_CONTENT)
def undo(
    req: HearthUndoRequest,
    _: None = Depends(require_hearth_device),
    db: Session = Depends(get_db),
) -> None:
    """Reverse a completion within the day (reuses scheduling.undo_completion
    — decay state only, never streaks or badges). An out-of-window undo is
    409; Hearth treats any non-2xx as "couldn't undo" and reconciles on its
    next poll. An owner may undo any completion; a member only their own."""
    member = _resolve_member(db, req.memberId)
    log = db.get(CompletionLog, _parse_int_id(req.completionId, "completionId"))
    if log is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Completion not found")
    if member.role != "owner" and log.completed_by != member.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "That completion isn't that member's to undo"
        )
    try:
        scheduling.undo_completion(
            db, log, tz=settings_service.user_timezone(db, member.id)
        )
    except (scheduling.UndoWindowClosed, scheduling.UndoNotLatest) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    db.commit()
