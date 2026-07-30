from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.room import Room
from app.models.supply import Supply
from app.models.task import Task
from app.models.user import User
from app.routers.auth import get_current_user, require_owner
from app.schemas.tasks import (
    CompleteRequest,
    CompleteResponse,
    SnoozeRequest,
    TaskCreate,
    TaskRead,
    TaskUpdate,
    task_to_read,
)
from app.services import campaigns as campaign_service
from app.services import reminder_service, scheduling, settings_service
from app.services import zones as zone_service
from app.services.push_service import notify_owners

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _get_task(db: Session, task_id: int) -> Task:
    task = db.scalar(
        select(Task).options(joinedload(Task.room)).where(Task.id == task_id)
    )
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return task


def _check_room(db: Session, room_id: int | None) -> None:
    if room_id is not None and db.get(Room, room_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Room not found")


def _check_assignee(db: Session, assignee_id: int | None) -> None:
    if assignee_id is not None and db.get(User, assignee_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Member not found")


def _fetch_supplies(db: Session, supply_ids: list[int]) -> list[Supply]:
    supplies = list(db.scalars(select(Supply).where(Supply.id.in_(supply_ids))).all())
    if len(supplies) != len(set(supply_ids)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Supply not found")
    return supplies


@router.get("", response_model=list[TaskRead])
def list_tasks(
    room_id: int | None = None,
    effort: str | None = None,
    category: str | None = None,
    include_inactive: bool = False,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> list[TaskRead]:
    """The global/task planning view (SPEC §6): the flat list, dirtiest
    first. Fresh and snoozed tasks are included here — planning shows
    everything; only the *doing* surfaces filter them out. The category
    param gives maintenance its own section without cluttering cleaning."""
    query = select(Task).options(joinedload(Task.room))
    if not include_inactive:
        query = query.where(Task.is_active.is_(True))
    if room_id is not None:
        query = query.where(Task.room_id == room_id)
    if effort in ("quick", "deep"):
        query = query.where(Task.effort == effort)
    if category in ("cleaning", "maintenance"):
        query = query.where(Task.category == category)

    tasks = scheduling.rank_tasks(
        list(db.scalars(query).all()),
        tz=settings_service.user_timezone(db, current_user.id),
    )
    return [task_to_read(task) for task in tasks]


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> TaskRead:
    _check_room(db, payload.room_id)
    _check_assignee(db, payload.assignee_id)
    task = Task(
        name=payload.name,
        room_id=payload.room_id,
        category=payload.category,
        cadence_days=payload.cadence_days,
        estimated_minutes=payload.estimated_minutes,
        effort=payload.effort,
        guest_facing=payload.guest_facing,
        preferred_day=payload.preferred_day,
        assignee_id=payload.assignee_id,
        claimable=payload.claimable,
        notes=payload.notes,
    )
    if payload.supply_ids:
        task.supplies = _fetch_supplies(db, payload.supply_ids)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task_to_read(task)


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> TaskRead:
    task = _get_task(db, task_id)

    if payload.name is not None:
        task.name = payload.name
    if payload.clear_room:
        task.room_id = None
    elif payload.room_id is not None:
        _check_room(db, payload.room_id)
        task.room_id = payload.room_id
    if payload.category is not None:
        task.category = payload.category
    if payload.cadence_days is not None:
        task.cadence_days = payload.cadence_days
    if payload.estimated_minutes is not None:
        task.estimated_minutes = payload.estimated_minutes
    if payload.effort is not None:
        task.effort = payload.effort
    if payload.guest_facing is not None:
        task.guest_facing = payload.guest_facing
    if payload.clear_preferred_day:
        task.preferred_day = None  # back to "no set day"
    elif payload.preferred_day is not None:
        task.preferred_day = payload.preferred_day
    if payload.clear_assignee:
        task.assignee_id = None
    elif payload.assignee_id is not None:
        _check_assignee(db, payload.assignee_id)
        task.assignee_id = payload.assignee_id
    if payload.claimable is not None:
        task.claimable = payload.claimable
    if payload.supply_ids is not None:
        task.supplies = _fetch_supplies(db, payload.supply_ids)
    if payload.notes is not None:
        task.notes = payload.notes or None
    if payload.is_active is not None:
        task.is_active = payload.is_active
    if payload.clear_last_done:
        task.last_done_at = None  # "never done" — back to high priority
    elif payload.last_done_at is not None:
        # A correction to history, not a completion: deliberately NO
        # CompletionLog, so it never inflates the done-today view or
        # streaks (Phase 5). The decay curve simply re-anchors.
        task.last_done_at = payload.last_done_at

    db.commit()
    db.refresh(task)
    return task_to_read(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> None:
    """Hard delete (history goes with it via cascade). The gentler option
    — archiving — is PATCH is_active=false."""
    task = _get_task(db, task_id)
    db.delete(task)
    db.commit()


def _can_complete(task: Task, user: User) -> bool:
    """The owner can complete anything. A kid can check off their own
    chores, or an unassigned one that was left open to claim (SPEC §6:
    'see their assigned/claimable chores and check them off')."""
    if user.role == "owner":
        return True
    if task.assignee_id == user.id:
        return True
    return task.claimable and task.assignee_id is None


@router.post("/{task_id}/complete", response_model=CompleteResponse)
def complete_task(
    task_id: int,
    payload: CompleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompleteResponse:
    """Done! Resets the decay curve and writes the CompletionLog (SPEC §4).
    Any pending snooze reminder is dropped so she's never nudged about
    finished work. A kid's completion notifies the owner (SPEC §6). The
    log row's id rides back so a mis-tap can be undone (Phase 9)."""
    task = _get_task(db, task_id)
    if not _can_complete(task, current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That one isn't yours to check off")

    # Whatever the lens, a running campaign that lists this task gets to
    # tick it off — progress is progress (SPEC §6, Phase 3). Marked
    # BEFORE complete_task so the Phase 5 badge check sees a campaign
    # this completion just finished.
    campaign_service.mark_done_in_running_campaigns(
        db, task.id, zone_service.local_today(db, current_user.id)
    )
    log = scheduling.complete_task(db, task, current_user, payload.source)
    completion_id = log.id  # read pre-commit; the object expires after
    reminder_service.clear_task_reminders(db, task.id)
    db.commit()

    if current_user.role == "kid":
        # After the commit, so the completion is durable no matter what
        # the push service does. Positive-only copy — this is a brag, not
        # an audit (SPEC §5/§6: notification, no gamification).
        first_name = current_user.name.split()[0]
        where = f" in the {task.room.name.lower()}" if task.room else ""
        notify_owners(db, "Ta-da! 🎉", f"{first_name} just checked off {task.name}{where}.")

    db.refresh(task)
    return CompleteResponse(**task_to_read(task).model_dump(), completion_id=completion_id)


@router.post("/{task_id}/claim", response_model=TaskRead)
def claim_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskRead:
    """Claim an up-for-grabs chore (SPEC §6: 'assigned to a member or left
    open to claim') — it becomes yours so nobody doubles up on it."""
    task = _get_task(db, task_id)
    if task.assignee_id == current_user.id:
        pass  # already theirs — claiming twice is harmless
    elif not task.is_active or not task.claimable or task.assignee_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That one's already spoken for")
    else:
        task.assignee_id = current_user.id
        db.commit()
    db.refresh(task)
    return task_to_read(task)


@router.post("/{task_id}/snooze", response_model=TaskRead)
def snooze_task(
    task_id: int,
    payload: SnoozeRequest,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> TaskRead:
    """Decay-aware snooze (SPEC §6): hides the task from doing-surfaces
    until the chosen time and schedules a gentle "ready when you are"
    reminder — last_done_at is untouched, so it keeps aging quietly."""
    task = _get_task(db, task_id)
    until = scheduling.snooze_task(task, payload.option)
    if payload.option == "wake":
        reminder_service.clear_task_reminders(db, task.id)
    else:
        reminder_service.create_snooze_reminder(db, current_user, task, until)
    db.commit()
    db.refresh(task)
    return task_to_read(task)
