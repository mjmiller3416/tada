"""The "what did I get done today" view (Phase 5).

Read entirely from the existing CompletionLog — completions were being
recorded all along; this is the first surface that plays them back.
Everything here is accumulation-only by design: what got done, the
current streak, badges earned. No denominators anywhere.
"""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.badge import Badge, UserBadge
from app.models.completion_log import CompletionLog
from app.models.task import Task
from app.models.user import User
from app.routers.auth import require_owner
from app.schemas.badges import badge_to_read
from app.schemas.done_today import DoneTodayEntry, DoneTodayResponse
from app.services import settings_service

router = APIRouter(prefix="/api/done-today", tags=["done-today"])


@router.get("", response_model=DoneTodayResponse)
def done_today(
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> DoneTodayResponse:
    """Today = her local calendar day (from Settings), not UTC's. Shows
    the whole household's completions with attribution ("is this
    handled"), her own streak, and her earned badges."""
    tz_name = settings_service.get_setting(db, current_user.id, "timezone")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    local_today = datetime.now(tz).date()
    day_start = datetime.combine(local_today, time.min, tzinfo=tz)
    day_end = day_start + timedelta(days=1)

    logs = db.scalars(
        select(CompletionLog)
        .join(Task, CompletionLog.task_id == Task.id)
        .options(joinedload(CompletionLog.task).joinedload(Task.room))
        .where(
            CompletionLog.completed_at >= day_start,
            CompletionLog.completed_at < day_end,
        )
        .order_by(CompletionLog.completed_at.desc())
    ).all()

    members = {u.id: u for u in db.scalars(select(User)).all()}

    earned = db.scalars(
        select(UserBadge)
        .join(Badge)
        .options(joinedload(UserBadge.badge))
        .where(UserBadge.user_id == current_user.id)
        .order_by(UserBadge.earned_at.desc())
    ).all()

    return DoneTodayResponse(
        date=local_today,
        completions=[
            DoneTodayEntry(
                id=log.id,
                task_name=log.task.name,
                room_id=log.task.room_id,
                room_name=log.task.room.name if log.task.room else None,
                completed_at=log.completed_at,
                completed_by_id=log.completed_by,
                completed_by_name=(
                    members[log.completed_by].name.split()[0]
                    if log.completed_by in members
                    else "Someone"
                ),
                source=log.source,
            )
            for log in logs
        ],
        streak=current_user.current_streak,
        badges=[badge_to_read(ub.badge, ub.earned_at) for ub in earned],
        household_members=len(members),
    )
