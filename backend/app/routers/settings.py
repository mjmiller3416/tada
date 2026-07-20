from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.settings import SettingsRead, SettingsUpdate
from app.services import reminder_service, settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _to_read(values: dict[str, str]) -> SettingsRead:
    return SettingsRead(
        daily_focus_count=int(values["daily_focus_count"]),
        default_session_minutes=int(values["default_session_minutes"]),
        daily_nudge_time=values["daily_nudge_time"],
        timezone=values["timezone"],
    )


@router.get("", response_model=SettingsRead)
def get_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SettingsRead:
    return _to_read(settings_service.get_settings(db, current_user.id))


@router.put("", response_model=SettingsRead)
def update_settings(
    payload: SettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SettingsRead:
    # None = leave untouched. daily_nudge_time="" is meaningful: nudge off.
    updates = {
        key: str(value)
        for key, value in payload.model_dump(exclude_unset=True).items()
        if value is not None
    }

    values = settings_service.set_settings(db, current_user.id, updates)
    # Nudge schedule follows the settings immediately.
    reminder_service.sync_daily_nudge(db, current_user)
    db.commit()
    return _to_read(values)
