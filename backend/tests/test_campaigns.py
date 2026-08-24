"""Campaign progress and its interaction with archiving and undo
(issues #28 and #15): archived tasks can't pin a campaign below 100%,
and undoing a completion takes back the checklist tick it made — unless
another completion inside the window still stands.
"""

from datetime import date, datetime, timedelta, timezone

from app.models.campaign import Campaign, CampaignTask
from app.services import campaigns as campaign_service
from app.services.scheduling import complete_task, undo_completion

NOW = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)


def _add_campaign(db, task_ids, start=date(2026, 7, 1), end=date(2026, 7, 31)):
    campaign = Campaign(
        name="Spring Cleaning", start_date=start, end_date=end, active=True
    )
    campaign.task_links = [CampaignTask(task_id=task_id) for task_id in task_ids]
    db.add(campaign)
    db.flush()
    return campaign


def _add_task(db, make_task, **overrides):
    overrides.setdefault("cadence_days", 7)
    overrides.setdefault("last_done_at", NOW - timedelta(days=10))
    task = make_task(**overrides)
    db.add(task)
    db.flush()
    return task


class TestProgressWithArchivedTasks:
    def test_an_archived_task_drops_out_of_the_denominator(self, db, make_task):
        """Issue #28: 10 tasks, 9 done, 1 archived — that's finished,
        not 90% forever."""
        done_tasks = [_add_task(db, make_task, name=f"t{i}") for i in range(3)]
        archived = _add_task(db, make_task, name="archived", is_active=False)
        campaign = _add_campaign(db, [t.id for t in done_tasks] + [archived.id])
        for link in campaign.task_links:
            if link.task_id != archived.id:
                link.done = True
        assert campaign_service.progress(campaign) == (3, 3)

    def test_a_done_then_archived_task_leaves_both_counts(self, db, make_task):
        finished = _add_task(db, make_task, name="finished", is_active=False)
        live = _add_task(db, make_task, name="live")
        campaign = _add_campaign(db, [finished.id, live.id])
        campaign.task_links[0].done = True
        assert campaign_service.progress(campaign) == (0, 1)


class TestUndoUnticksTheCampaign:
    def test_undo_takes_the_tick_back(self, db, make_task, owner):
        """Issue #15: mis-tap Done, undo — the checklist and its percent
        must both come back down."""
        task = _add_task(db, make_task)
        campaign = _add_campaign(db, [task.id])
        campaign_service.mark_done_in_running_campaigns(db, task.id, NOW.date())
        log = complete_task(db, task, owner, "direct", NOW)
        assert campaign.task_links[0].done is True
        undo_completion(db, log, NOW)
        assert campaign.task_links[0].done is False
        assert campaign_service.progress(campaign) == (0, 1)

    def test_tick_survives_when_an_earlier_in_window_completion_stands(
        self, db, make_task, owner
    ):
        # Done for real on the 5th (inside the window), done again today
        # by mistake — undoing today's keeps the "did it this spring".
        task = _add_task(db, make_task)
        campaign = _add_campaign(db, [task.id])
        earlier = NOW - timedelta(days=5)
        campaign_service.mark_done_in_running_campaigns(db, task.id, earlier.date())
        complete_task(db, task, owner, "direct", earlier)
        log = complete_task(db, task, owner, "direct", NOW)
        undo_completion(db, log, NOW)
        assert campaign.task_links[0].done is True

    def test_out_of_window_completions_do_not_hold_the_tick(
        self, db, make_task, owner
    ):
        # The only other completion predates the campaign — it can't
        # back a "did it this spring" tick.
        task = _add_task(db, make_task)
        campaign = _add_campaign(db, [task.id])
        before_window = NOW - timedelta(days=30)
        complete_task(db, task, owner, "direct", before_window)
        campaign_service.mark_done_in_running_campaigns(db, task.id, NOW.date())
        log = complete_task(db, task, owner, "direct", NOW)
        undo_completion(db, log, NOW)
        assert campaign.task_links[0].done is False
