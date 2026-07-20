from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.room import Room
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.onboarding import OnboardingRequest, OnboardingResponse
from app.services import reminder_service, starter_tasks

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


@router.post("", response_model=OnboardingResponse)
def run_onboarding(
    payload: OnboardingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OnboardingResponse:
    """The onboarding wizard's generate step (SPEC §6): create the rooms
    and auto-generate a starter schedule per room, tuned by household
    context. Safe to run again later — it only ever adds. Also makes sure
    the daily nudge reminder exists now that there's something to nudge
    about."""
    next_order = db.scalar(select(func.coalesce(func.max(Room.sort_order), -1))) + 1

    tasks_created = 0
    for index, entry in enumerate(payload.rooms):
        room = Room(name=entry.name, sort_order=next_order + index)
        db.add(room)
        db.flush()  # assign room.id before tasks reference it
        created = starter_tasks.generate_for_room(
            db,
            room,
            entry.type,
            has_pets=payload.has_pets,
            has_kids=payload.has_kids,
        )
        tasks_created += len(created)

    reminder_service.sync_daily_nudge(db, current_user)
    db.commit()

    return OnboardingResponse(
        rooms_created=len(payload.rooms), tasks_created=tasks_created
    )
