"""Seasonal campaigns (SPEC §6, Phase 3).

An episodic overlay: a named bundle of tasks with a date window and a
progress rollup. The campaign never replaces the decay engine — its
tasks are ordinary tasks that keep decaying — it just adds a checklist
("did it this spring") and doles the remaining work out a few tasks a
day across the window.
"""

import math
from datetime import date, tzinfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.campaign import Campaign, CampaignTask
from app.models.task import Task
from app.services import scheduling


def is_running(campaign: Campaign, today: date) -> bool:
    """Active and inside its date window — the state where the campaign
    surfaces on the home screen and builds sessions."""
    return campaign.active and campaign.start_date <= today <= campaign.end_date


def progress(campaign: Campaign) -> tuple[int, int]:
    """(done, total) across the campaign's checklist."""
    total = len(campaign.task_links)
    done = sum(1 for link in campaign.task_links if link.done)
    return done, total


def today_slice(
    db: Session, campaign: Campaign, today: date, tz: tzinfo | None = None
) -> list[Task]:
    """The campaign tasks to offer today (SPEC §6: "spread over days").

    Remaining work divided evenly across the days left in the window
    (ceiling, so it always suggests at least one while anything remains).
    Past the end date, whatever's left just comes in session-sized
    chunks — a campaign that ran long is never scolded, it's simply
    finished at her pace. Ranked by the same decay priority as
    everything else, capped at the session cap."""
    remaining_ids = [
        link.task_id for link in campaign.task_links if not link.done
    ]
    if not remaining_ids:
        return []

    tasks = list(
        db.scalars(
            select(Task).where(Task.id.in_(remaining_ids), Task.is_active.is_(True))
        ).all()
    )
    ranked = scheduling.rank_tasks(tasks, tz=tz)

    days_left = max((campaign.end_date - max(today, campaign.start_date)).days + 1, 1)
    per_day = math.ceil(len(ranked) / days_left)
    return ranked[: min(per_day, scheduling.MAX_SESSION_TASKS)]


def mark_done_in_running_campaigns(db: Session, task_id: int, today: date) -> None:
    """Tick this task off every running campaign that includes it.

    Called on *every* completion, whatever the lens — if she cleans the
    windows during a room session, the Spring Cleaning checklist should
    notice. Progress is progress. Caller commits."""
    links = db.scalars(
        select(CampaignTask)
        .join(Campaign)
        .where(
            CampaignTask.task_id == task_id,
            CampaignTask.done.is_(False),
            Campaign.active.is_(True),
            Campaign.start_date <= today,
            Campaign.end_date >= today,
        )
    ).all()
    for link in links:
        link.done = True
