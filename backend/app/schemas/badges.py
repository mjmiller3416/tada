from datetime import datetime

from pydantic import BaseModel

from app.models.badge import Badge


class BadgeRead(BaseModel):
    """An earned badge as every surface shows it — always with its
    earned_at, because we only ever list badges she actually has
    (SPEC §5: accumulation, never a checklist of the unearned)."""

    id: int
    code: str
    name: str
    description: str
    emoji: str
    earned_at: datetime


def badge_to_read(badge: Badge, earned_at: datetime) -> BadgeRead:
    return BadgeRead(
        id=badge.id,
        code=badge.code,
        name=badge.name,
        description=badge.description,
        emoji=badge.emoji,
        earned_at=earned_at,
    )
