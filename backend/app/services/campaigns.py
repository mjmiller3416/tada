"""Seasonal campaigns (SPEC §6, Phase 3).

An episodic overlay: a named bundle of tasks with a date window and a
progress rollup. The campaign never replaces the decay engine — its
tasks are ordinary tasks that keep decaying — it just adds a checklist
("did it this spring") and doles the remaining work out a few tasks a
day across the window.
"""

import math
from datetime import date, timezone, tzinfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.campaign import Campaign, CampaignTask
from app.models.completion_log import CompletionLog
from app.models.task import Task
from app.services import scheduling


def is_running(campaign: Campaign, today: date) -> bool:
    """Active and inside its date window — the state where the campaign
    surfaces on the home screen and builds sessions."""
    return campaign.active and campaign.start_date <= today <= campaign.end_date


def live_links(campaign: Campaign) -> list[CampaignTask]:
    """The checklist rows progress and the detail view count (issue
    #28): archived tasks drop out — a task archived mid-window can never
    be offered or completed again, so counting it would pin the campaign
    below 100% forever. With every task archived, the full checklist is
    the honest picture (a finished-then-retired campaign stays 100%,
    never a hollow 0/0)."""
    live = [link for link in campaign.task_links if link.task.is_active]
    return live or list(campaign.task_links)


def progress(campaign: Campaign) -> tuple[int, int]:
    """(done, total) across the campaign's live checklist (see
    live_links)."""
    links = live_links(campaign)
    done = sum(1 for link in links if link.done)
    return done, len(links)


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


def untick_for_undone_completion(
    db: Session, log: CompletionLog, local: tzinfo
) -> None:
    """Reverse the tick `mark_done_in_running_campaigns` made for a
    completion being undone (issue #15): a checklist tick means "did it
    during this campaign", so it only survives the undo if ANOTHER
    completion of the task still falls inside that campaign's window.
    `log` is the row about to be deleted; `local` is her timezone (the
    same clock the tick's `today` came from). Caller commits."""

    def local_day(completed_at) -> date:
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=timezone.utc)
        return completed_at.astimezone(local).date()

    undone_day = local_day(log.completed_at)
    links = db.scalars(
        select(CampaignTask)
        .join(Campaign)
        .where(
            CampaignTask.task_id == log.task_id,
            CampaignTask.done.is_(True),
            # The mirror of mark_done_in_running_campaigns: only ticks a
            # running campaign could have made are candidates to reverse.
            Campaign.active.is_(True),
            Campaign.start_date <= undone_day,
            Campaign.end_date >= undone_day,
        )
    ).all()
    if not links:
        return

    remaining_days = {
        local_day(completed_at)
        for completed_at in db.scalars(
            select(CompletionLog.completed_at).where(
                CompletionLog.task_id == log.task_id, CompletionLog.id != log.id
            )
        ).all()
    }
    for link in links:
        window = link.campaign
        if not any(
            window.start_date <= day <= window.end_date for day in remaining_days
        ):
            link.done = False
