from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.room import Room
from app.models.task import Task
from app.models.user import User
from app.routers.auth import require_owner
from app.schemas.rooms import RoomCreate, RoomRead, RoomUpdate
from app.services import scheduling

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


def _room_to_read(room: Room, tasks: list[Task]) -> RoomRead:
    active = [t for t in tasks if t.is_active]
    ratio = scheduling.room_aggregate_ratio(active)
    due = sum(
        1
        for t in active
        if scheduling.dirtiness_ratio(t) >= scheduling.BAND_DUE
        and not scheduling.is_snoozed(t)
    )
    return RoomRead(
        id=room.id,
        name=room.name,
        sort_order=room.sort_order,
        ratio=round(ratio, 3) if ratio is not None else None,
        band=scheduling.band_for_ratio(ratio) if ratio is not None else None,
        task_count=len(active),
        due_count=due,
    )


@router.get("", response_model=list[RoomRead])
def list_rooms(
    _: User = Depends(require_owner), db: Session = Depends(get_db)
) -> list[RoomRead]:
    rooms = db.scalars(select(Room).order_by(Room.sort_order, Room.id)).all()
    tasks = db.scalars(select(Task).where(Task.room_id.is_not(None))).all()
    by_room: dict[int, list[Task]] = {}
    for task in tasks:
        by_room.setdefault(task.room_id, []).append(task)
    return [_room_to_read(room, by_room.get(room.id, [])) for room in rooms]


@router.post("", response_model=RoomRead, status_code=status.HTTP_201_CREATED)
def create_room(
    payload: RoomCreate,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> RoomRead:
    next_order = db.scalar(select(func.coalesce(func.max(Room.sort_order), -1))) + 1
    room = Room(name=payload.name, sort_order=next_order)
    db.add(room)
    db.commit()
    db.refresh(room)
    return _room_to_read(room, [])


@router.patch("/{room_id}", response_model=RoomRead)
def update_room(
    room_id: int,
    payload: RoomUpdate,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> RoomRead:
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Room not found")
    if payload.name is not None:
        room.name = payload.name
    if payload.sort_order is not None:
        room.sort_order = payload.sort_order
    db.commit()
    tasks = db.scalars(select(Task).where(Task.room_id == room.id)).all()
    return _room_to_read(room, list(tasks))


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_room(
    room_id: int,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> None:
    """Deletes the room only — its tasks stay (room_id set NULL by the FK)
    and remain visible in the global task view under "no room"."""
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Room not found")
    db.delete(room)
    db.commit()
