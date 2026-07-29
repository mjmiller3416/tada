"""Badge awarding (SPEC §5: badges not levels, positive-only).

Evaluated after every completion (via scheduling.complete_task) and
again at session complete (the "session-complete celebration + badge
check" SPEC §5 describes). Strictly idempotent: the earned check and
the (user_id, badge_id) unique constraint mean a badge is awarded once
and never twice — and nothing here ever revokes one.

Badges are small gifts, not certifications — the copy below is warm and
specific on purpose. Kids are deliberately excluded: SPEC §6 says no
points, rewards, or gamification for the kids' chores.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.badge import Badge, UserBadge
from app.models.campaign import Campaign, CampaignTask
from app.models.completion_log import CompletionLog
from app.models.user import User
from app.services import settings_service

#: A completion at or before this local hour counts as an early bird.
EARLY_BIRD_HOUR = 8

#: The seed set — every badge computable from CompletionLog + User (plus
#: the campaign checklist for campaign_first). `code` is the stable
#: identity; edits to name/description/emoji flow through on deploy.
SEED_BADGES: list[dict] = [
    {
        "code": "first_task",
        "name": "First Ta-da!",
        "description": "Your very first task, done and dusted. It all starts here.",
        "emoji": "🎉",
        "criteria_key": "completions_1",
        "sort_order": 1,
    },
    {
        "code": "tasks_10",
        "name": "Perfect Ten",
        "description": "Ten tasks checked off. Quietly unstoppable.",
        "emoji": "✨",
        "criteria_key": "completions_10",
        "sort_order": 2,
    },
    {
        "code": "tasks_50",
        "name": "Nifty Fifty",
        "description": "Fifty tasks done. That's a whole lot of love for one home.",
        "emoji": "🌟",
        "criteria_key": "completions_50",
        "sort_order": 3,
    },
    {
        "code": "tasks_100",
        "name": "The Hundred Club",
        "description": "One hundred tasks. Your home is lucky to have you.",
        "emoji": "💯",
        "criteria_key": "completions_100",
        "sort_order": 4,
    },
    {
        "code": "streak_3",
        "name": "Three in a Row",
        "description": "Three days running — a little rhythm going.",
        "emoji": "🔥",
        "criteria_key": "streak_3",
        "sort_order": 5,
    },
    {
        "code": "streak_7",
        "name": "A Whole Week",
        "description": "Seven days straight. That's a habit being born.",
        "emoji": "🗓️",
        "criteria_key": "streak_7",
        "sort_order": 6,
    },
    {
        "code": "streak_30",
        "name": "Thirty Days of Sparkle",
        "description": "A month of showing up. Genuinely remarkable.",
        "emoji": "💎",
        "criteria_key": "streak_30",
        "sort_order": 7,
    },
    {
        "code": "session_first",
        "name": "First Sprint",
        "description": "A whole focus session, start to finish. Ta-da indeed.",
        "emoji": "🏁",
        "criteria_key": "session_complete",
        "sort_order": 8,
    },
    {
        "code": "guest_rescue",
        "name": "Guest Rescue",
        "description": "Company was coming — and you were ready.",
        "emoji": "🛎️",
        "criteria_key": "source_guest_mode",
        "sort_order": 9,
    },
    {
        "code": "zone_first",
        "name": "Zone Explorer",
        "description": "Your first zone task. FlyLady would be proud.",
        "emoji": "🧭",
        "criteria_key": "source_zone",
        "sort_order": 10,
    },
    {
        "code": "campaign_first",
        "name": "Campaign Finisher",
        "description": "A whole seasonal campaign, wrapped up with a bow.",
        "emoji": "🌷",
        "criteria_key": "campaign_complete",
        "sort_order": 11,
    },
    {
        "code": "early_bird",
        "name": "Early Bird",
        "description": "Something done before 8am. The day never saw it coming.",
        "emoji": "🐦",
        "criteria_key": "early_bird",
        "sort_order": 12,
    },
]


def seed_badges(db: Session) -> None:
    """Insert any seed badges missing by code — idempotent, and later
    phases can grow the set the same way (same pattern as the packing
    templates and FlyLady zones). Never overwrites an existing row.
    Caller commits."""
    existing = set(db.scalars(select(Badge.code)).all())
    for fields in SEED_BADGES:
        if fields["code"] not in existing:
            db.add(Badge(**fields))
    db.flush()


def _local_hour(db: Session, user_id: int, now: datetime) -> int:
    tz_name = settings_service.get_setting(db, user_id, "timezone")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    return now.astimezone(tz).hour


def _completion_count(db: Session, user_id: int) -> int:
    return (
        db.scalar(
            select(func.count(CompletionLog.id)).where(
                CompletionLog.completed_by == user_id
            )
        )
        or 0
    )


def _has_source(db: Session, user_id: int, source: str) -> bool:
    return (
        db.scalar(
            select(CompletionLog.id)
            .where(CompletionLog.completed_by == user_id, CompletionLog.source == source)
            .limit(1)
        )
        is not None
    )


def _any_campaign_finished(db: Session) -> bool:
    """A campaign counts as finished when it has tasks and every one is
    ticked. Household-wide on purpose — a campaign is a family project."""
    campaigns = db.scalars(select(Campaign.id)).all()
    for campaign_id in campaigns:
        total = db.scalar(
            select(func.count(CampaignTask.task_id)).where(
                CampaignTask.campaign_id == campaign_id
            )
        )
        if not total:
            continue
        done = db.scalar(
            select(func.count(CampaignTask.task_id)).where(
                CampaignTask.campaign_id == campaign_id, CampaignTask.done.is_(True)
            )
        )
        if done == total:
            return True
    return False


def _criteria_met(
    db: Session,
    user: User,
    criteria_key: str,
    *,
    now: datetime,
    session_completed: bool,
) -> bool:
    """One badge criterion. Every check reads durable state (CompletionLog,
    User, the campaign checklist) except the two moment-badges: early_bird
    checks the completion happening right now, and session_complete only
    fires from the session-complete call."""
    if criteria_key.startswith("completions_"):
        return _completion_count(db, user.id) >= int(criteria_key.split("_")[1])
    if criteria_key.startswith("streak_"):
        # longest_streak so a milestone is never missed if the streak
        # resets between the moment it was reached and this check.
        return user.longest_streak >= int(criteria_key.split("_")[1])
    if criteria_key.startswith("source_"):
        return _has_source(db, user.id, criteria_key.removeprefix("source_"))
    if criteria_key == "campaign_complete":
        return _any_campaign_finished(db)
    if criteria_key == "early_bird":
        return _local_hour(db, user.id, now) < EARLY_BIRD_HOUR and _completion_count(
            db, user.id
        ) > 0
    if criteria_key == "session_complete":
        return session_completed
    return False


def _evaluate(
    db: Session, user: User, now: datetime, *, session_completed: bool
) -> list[Badge]:
    """Award every not-yet-earned badge whose criterion now holds.
    Returns the newly earned badges (for celebrating). Caller commits."""
    if user.role != "owner":
        return []  # SPEC §6: no gamification for the kids' chores

    seed_badges(db)
    earned_ids = set(
        db.scalars(select(UserBadge.badge_id).where(UserBadge.user_id == user.id)).all()
    )
    badges = db.scalars(select(Badge).order_by(Badge.sort_order)).all()

    new_badges: list[Badge] = []
    for badge in badges:
        if badge.id in earned_ids:
            continue
        if _criteria_met(
            db, user, badge.criteria_key, now=now, session_completed=session_completed
        ):
            # Savepoint per award: if a concurrent completion won the
            # race to this badge, only the duplicate award rolls back —
            # never the completion it was riding on.
            try:
                with db.begin_nested():
                    db.add(UserBadge(user_id=user.id, badge_id=badge.id, earned_at=now))
                    db.flush()
                new_badges.append(badge)
            except IntegrityError:
                pass  # already earned — exactly once, never twice
    return new_badges


def evaluate_completion(
    db: Session, user: User, now: datetime | None = None
) -> list[Badge]:
    """The after-a-completion check (called from complete_task, after the
    CompletionLog row is flushed). Caller commits."""
    now = now or datetime.now(timezone.utc)
    return _evaluate(db, user, now, session_completed=False)


def evaluate_session_complete(
    db: Session, user: User, tasks_done: int, now: datetime | None = None
) -> list[Badge]:
    """The session-complete check (SPEC §5's "celebration + badge check").
    A session only counts toward session_first when something actually
    got done in it — showing up matters, but the badge marks a first
    finished sprint. Caller commits."""
    now = now or datetime.now(timezone.utc)
    return _evaluate(db, user, now, session_completed=tasks_done >= 1)
