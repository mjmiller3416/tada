from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.badges import BadgeRead


class DoneTodayEntry(BaseModel):
    """One completion from today's CompletionLog. Attribution answers
    "is this handled" — never "who's pulling their weight" (SPEC §5)."""

    id: int
    task_name: str
    room_id: int | None
    room_name: str | None
    completed_at: datetime
    completed_by_id: int
    completed_by_name: str
    source: str


class DoneTodayResponse(BaseModel):
    """The Done Today view: accumulation only. Deliberately no totals to
    hit, no denominators, no percentages — a denominator would turn the
    reward into a scoreboard and invert the no-guilt design."""

    date: date  # her local day the entries belong to
    completions: list[DoneTodayEntry]
    streak: int  # the current number, shown warmly, nothing else
    badges: list[BadgeRead]  # earned only — never a checklist of the unearned
    household_members: int  # >1 = show who did what on each entry
