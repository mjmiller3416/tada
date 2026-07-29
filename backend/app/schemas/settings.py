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


class SettingsUpdate(BaseModel):
    daily_focus_count: int | None = Field(default=None, ge=1, le=3)
    default_session_minutes: int | None = Field(default=None, ge=5, le=240)
    daily_nudge_time: str | None = None
    timezone: str | None = None
    zones_enabled: bool | None = None
    campaigns_enabled: bool | None = None
    vacation_until: str | None = None

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
