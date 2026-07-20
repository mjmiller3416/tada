from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.room import Room
from app.models.task import Task
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.tasks import (
    CompleteRequest,
    SnoozeRequest,
    TaskCreate,
    TaskRead,
    TaskUpdate,
    task_to_read,
)
from app.services import reminder_service, scheduling

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


@router.get("", response_model=list[TaskRead])
def list_tasks(
    room_id: int | None = None,
    effort: str | None = None,
    include_inactive: bool = False,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TaskRead]:
    """The global/task planning view (SPEC §6): the flat list, dirtiest
    first. Fresh and snoozed tasks are included here — planning shows
    everything; only the *doing* surfaces filter them out."""
    query = select(Task).options(joinedload(Task.room))
    if not include_inactive:
        query = query.where(Task.is_active.is_(True))
    if room_id is not None:
        query = query.where(Task.room_id == room_id)
    if effort in ("quick", "deep"):
        query = query.where(Task.effort == effort)

    tasks = scheduling.rank_tasks(list(db.scalars(query).all()))
    return [task_to_read(task) for task in tasks]


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskRead:
    _check_room(db, payload.room_id)
    task = Task(
        name=payload.name,
        room_id=payload.room_id,
        cadence_days=payload.cadence_days,
        estimated_minutes=payload.estimated_minutes,
        effort=payload.effort,
        guest_facing=payload.guest_facing,
        notes=payload.notes,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task_to_read(task)


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    _: User = Depends(get_current_user),
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
    if payload.cadence_days is not None:
        task.cadence_days = payload.cadence_days
    if payload.estimated_minutes is not None:
        task.estimated_minutes = payload.estimated_minutes
    if payload.effort is not None:
        task.effort = payload.effort
    if payload.guest_facing is not None:
        task.guest_facing = payload.guest_facing
    if payload.notes is not None:
        task.notes = payload.notes or None
    if payload.is_active is not None:
        task.is_active = payload.is_active

    db.commit()
    db.refresh(task)
    return task_to_read(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Hard delete (history goes with it via cascade). The gentler option
    — archiving — is PATCH is_active=false."""
    task = _get_task(db, task_id)
    db.delete(task)
    db.commit()


@router.post("/{task_id}/complete", response_model=TaskRead)
def complete_task(
    task_id: int,
    payload: CompleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskRead:
    """Done! Resets the decay curve and writes the CompletionLog (SPEC §4).
    Any pending snooze reminder is dropped so she's never nudged about
    finished work."""
    task = _get_task(db, task_id)
    scheduling.complete_task(db, task, current_user, payload.source)
    reminder_service.clear_task_reminders(db, task.id)
    db.commit()
    db.refresh(task)
    return task_to_read(task)


@router.post("/{task_id}/snooze", response_model=TaskRead)
def snooze_task(
    task_id: int,
    payload: SnoozeRequest,
    current_user: User = Depends(get_current_user),
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
