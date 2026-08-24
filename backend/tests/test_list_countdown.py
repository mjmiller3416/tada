"""The list countdown reminder's lead time (issue #19): the chosen
days-before is persisted on the reminder row ("list_countdown:<n>") and
survives re-syncs that don't choose a new one — a rename or archive
round-trip must never quietly snap a 14-day lead back to the default 3.
"""

from datetime import date, timedelta

from sqlalchemy import select

from app.models.lists import List
from app.models.reminder import Reminder
from app.services import lists as list_service


def _add_list(db, event_in_days=30):
    parent = List(
        name="Beach trip",
        kind="packing",
        is_template=False,
        event_date=date.today() + timedelta(days=event_in_days),
        status="active",
    )
    db.add(parent)
    db.flush()
    return parent


def _countdown(db, list_id) -> Reminder:
    db.flush()  # the service leaves the flush/commit to the router
    return db.scalar(select(Reminder).where(Reminder.list_id == list_id))


class TestCountdownLeadPersists:
    def test_the_chosen_lead_is_stored_on_the_rule(self, db, owner):
        parent = _add_list(db)
        list_service.sync_countdown_reminder(db, owner, parent, True, 14)
        reminder = _countdown(db, parent.id)
        assert reminder.recurrence_rule == "list_countdown:14"
        # First nudge lands 14 days out, not 3.
        assert reminder.scheduled_for.date() == parent.event_date - timedelta(days=14)

    def test_a_resync_without_a_choice_keeps_the_persisted_lead(self, db, owner):
        parent = _add_list(db)
        list_service.sync_countdown_reminder(db, owner, parent, True, 14)
        db.flush()  # in production a commit separates the two PATCHes
        # The issue-#19 scenario: a later PATCH re-syncs without naming a
        # lead (days_before=None) — e.g. an event-date change.
        parent.event_date = parent.event_date + timedelta(days=7)
        list_service.sync_countdown_reminder(db, owner, parent, True, None)
        reminder = _countdown(db, parent.id)
        assert reminder.recurrence_rule == "list_countdown:14"
        assert reminder.scheduled_for.date() == parent.event_date - timedelta(days=14)

    def test_a_pre_fix_row_without_a_suffix_falls_back_to_the_default(
        self, db, owner
    ):
        parent = _add_list(db)
        list_service.sync_countdown_reminder(db, owner, parent, True, None)
        reminder = _countdown(db, parent.id)
        assert reminder.recurrence_rule == (
            f"list_countdown:{list_service.DEFAULT_REMINDER_DAYS_BEFORE}"
        )
