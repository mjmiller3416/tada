import re
from datetime import date
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class SettingsRead(BaseModel):
    daily_focus_count: int
    default_session_minutes: int
    daily_nudge_time: str  # "HH:MM", or "" when the nudge is off
    timezone: str
    zones_enabled: bool
    campaigns_enabled: bool
    vacation_until: str  # "YYYY-MM-DD" (last paused day), or "" when home
    # Phase 11: the scheduling-lanes flag (flips on after the
    # reclassification review) and Zone 3's rotating second room (a room
    # id as a string, "" = none this rotation).
    zone_lane_enabled: bool
    zone_3_extra_room_id: str


class SettingsUpdate(BaseModel):
    daily_focus_count: int | None = Field(default=None, ge=1, le=3)
    default_session_minutes: int | None = Field(default=None, ge=5, le=240)
    daily_nudge_time: str | None = None
    timezone: str | None = None
    zones_enabled: bool | None = None
    campaigns_enabled: bool | None = None
    vacation_until: str | None = None
    zone_lane_enabled: bool | None = None
    zone_3_extra_room_id: str | None = None

    @field_validator("zone_3_extra_room_id")
    @classmethod
    def validate_extra_room(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return value  # "" is meaningful: no extra room this rotation
        if not value.isdigit():
            raise ValueError("must be a room id, or empty for no extra room")
        return value

    @field_validator("daily_nudge_time")
    @classmethod
    def validate_nudge_time(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return value
        if not _TIME_RE.match(value):
            raise ValueError("must be HH:MM (24-hour) or empty to turn the nudge off")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except Exception as exc:
            raise ValueError("must be a valid IANA timezone name") from exc
        return value

    @field_validator("vacation_until")
    @classmethod
    def validate_vacation_until(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return value  # "" is meaningful: vacation mode off
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                "must be a date (YYYY-MM-DD) or empty to turn vacation mode off"
            ) from exc
        return value
