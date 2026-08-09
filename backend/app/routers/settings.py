from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.routers.auth import require_owner
from app.schemas.settings import SettingsRead, SettingsUpdate
from app.services import reminder_service, settings_service
from app.services import zones as zone_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _to_read(values: dict[str, str]) -> SettingsRead:
    return SettingsRead(
        daily_focus_count=int(values["daily_focus_count"]),
        default_session_minutes=int(values["default_session_minutes"]),
        daily_nudge_time=values["daily_nudge_time"],
        timezone=values["timezone"],
        zones_enabled=values["zones_enabled"] == "true",
        campaigns_enabled=values["campaigns_enabled"] == "true",
        vacation_until=values["vacation_until"],
        zone_lane_enabled=values["zone_lane_enabled"] == "true",
        zone_3_extra_room_id=values["zone_3_extra_room_id"],
    )


def _to_stored(value: object) -> str:
    """Settings store as strings; booleans as "true"/"false"."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


@router.get("", response_model=SettingsRead)
def get_settings(
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> SettingsRead:
    return _to_read(settings_service.get_settings(db, current_user.id))


@router.put("", response_model=SettingsRead)
def update_settings(
    payload: SettingsUpdate,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> SettingsRead:
    # None = leave untouched. daily_nudge_time="" is meaningful: nudge off.
    updates = {
        key: _to_stored(value)
        for key, value in payload.model_dump(exclude_unset=True).items()
        if value is not None
    }

    # "I'm back" (Phase 4.6) clears vacation_until — first fold the days
    # already spent away into the streak freeze (Phase 5), so an early
    # return never reads as a streak break.
    if updates.get("vacation_until") == "":
        settings_service.record_vacation_clear(
            db, current_user.id, zone_service.local_today(db, current_user.id)
        )

    before = settings_service.get_settings(db, current_user.id)
    values = settings_service.set_settings(db, current_user.id, updates)
    # Re-sync the nudge only when its inputs actually changed. The sync
    # always recomputes scheduled_for strictly-after-now, so running it
    # on every save meant toggling ANY setting inside the nudge's due
    # window silently swallowed that day's nudge (issue #24). Compare
    # values, not payload keys — the settings form sends every field.
    if any(values[key] != before[key] for key in ("daily_nudge_time", "timezone")):
        reminder_service.sync_daily_nudge(db, current_user)
    db.commit()
    return _to_read(values)
