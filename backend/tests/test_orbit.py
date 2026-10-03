"""Tests for the Orbit integration API (routers/orbit.py).

Router-level tests drive the real FastAPI app through TestClient with the
in-memory SQLite session injected via a get_db override, the same pattern
as test_hearth.py. The token is monkeypatched on the shared settings
singleton, which both the router dependency and
auth_service.verify_orbit_token read. Pure tests cover the two scheduling
helpers Orbit added (chore_due_at, check_undoable): SPEC §4, anything
touching the decay engine needs tests.
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.config import settings as app_settings
from app.database import get_db
from app.main import app
from app.models import CompletionLog, Room, Setting, User
from app.services import orbit as orbit_service
from app.services import scheduling

TOKEN = "orbit-test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def ago(days: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


@pytest.fixture()
def client(db, monkeypatch):
    """The real app, wired to the test session, with Orbit configured and
    Hearth deliberately NOT configured (the two must be independent)."""
    monkeypatch.setattr(app_settings, "orbit_api_token", TOKEN)
    monkeypatch.setattr(app_settings, "hearth_device_token", "")
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def link(db):
    user = User(name="Link", password_hash="x", role="kid")
    db.add(user)
    db.flush()
    return user


def _room(db, name):
    room = Room(name=name, sort_order=0)
    db.add(room)
    db.flush()
    return room


def _task(db, make_task, **overrides):
    task = make_task(**overrides)
    db.add(task)
    db.flush()
    return task


def _board(client, member):
    r = client.get(f"/api/orbit/chores?member={member.id}", headers=AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def _by_name(chores):
    return {c["name"]: c for c in chores}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestAuth:
    def test_unconfigured_is_503(self, client, monkeypatch):
        monkeypatch.setattr(app_settings, "orbit_api_token", "")
        r = client.get("/api/orbit/members", headers=AUTH)
        assert r.status_code == 503
        assert r.json() == {"detail": "Orbit integration is not configured"}

    def test_missing_header_is_401(self, client):
        assert client.get("/api/orbit/members").status_code == 401

    def test_wrong_token_is_401(self, client):
        r = client.get("/api/orbit/members", headers={"Authorization": "Bearer nope"})
        assert r.status_code == 401

    def test_non_bearer_is_401(self, client):
        r = client.get("/api/orbit/members", headers={"Authorization": TOKEN})
        assert r.status_code == 401

    def test_hearth_token_does_not_open_orbit(self, client, monkeypatch):
        monkeypatch.setattr(app_settings, "hearth_device_token", "hearth-token")
        r = client.get(
            "/api/orbit/members", headers={"Authorization": "Bearer hearth-token"}
        )
        assert r.status_code == 401

    def test_orbit_token_does_not_open_hearth(self, client, monkeypatch):
        monkeypatch.setattr(app_settings, "hearth_device_token", "hearth-token")
        assert client.get("/api/hearth/rooms", headers=AUTH).status_code == 401

    def test_valid_token_passes(self, client):
        assert client.get("/api/orbit/members", headers=AUTH).status_code == 200

    @pytest.mark.parametrize(
        "method,path",
        [
            ("get", "/api/orbit/chores?member=1"),
            ("get", "/api/orbit/completions?member=1"),
            ("post", "/api/orbit/complete"),
            ("post", "/api/orbit/undo"),
        ],
    )
    def test_every_route_is_gated(self, client, method, path):
        assert getattr(client, method)(path).status_code == 401


# ---------------------------------------------------------------------------
# GET /members
# ---------------------------------------------------------------------------

def test_members_lists_everyone_with_string_ids(client, db, owner, link):
    db.commit()
    body = client.get("/api/orbit/members", headers=AUTH).json()
    assert body == {
        "members": [
            {"id": str(owner.id), "name": "Maryann", "role": "owner"},
            {"id": str(link.id), "name": "Link", "role": "kid"},
        ]
    }


# ---------------------------------------------------------------------------
# GET /chores
# ---------------------------------------------------------------------------

class TestChores:
    def test_unknown_member_is_404(self, client, db, owner):
        db.commit()
        assert client.get("/api/orbit/chores?member=999", headers=AUTH).status_code == 404
        assert client.get("/api/orbit/chores?member=abc", headers=AUTH).status_code == 404

    def test_shape_and_household_clock(self, client, db, owner, link):
        db.commit()
        body = _board(client, link)
        assert body["member"] == {"id": str(link.id), "name": "Link"}
        assert body["timezone"] == "UTC"  # the owner fixture pins UTC
        assert body["date"] == utc_today().isoformat()
        assert set(body) == {"member", "date", "timezone", "today", "upcoming", "recurring", "stats"}

    def test_timezone_is_the_owners(self, client, db, owner, link):
        setting = db.query(Setting).filter_by(user_id=owner.id, key="timezone").one()
        setting.value = "America/Chicago"
        db.commit()
        body = _board(client, link)
        assert body["timezone"] == "America/Chicago"
        assert body["date"] == datetime.now(ZoneInfo("America/Chicago")).date().isoformat()

    def test_today_upcoming_recurring(self, client, db, make_task, owner, link):
        kitchen = _room(db, "Kitchen")
        other_kid = User(name="Zelda", password_hash="x", role="kid")
        db.add(other_kid)
        db.flush()
        dishes = _task(
            db, make_task, name="Empty dishwasher", assignee_id=link.id,
            cadence_days=1, last_done_at=ago(2), room_id=kitchen.id,
            notes="Plates go on the left", estimated_minutes=5, preferred_day=0,
        )
        _task(
            db, make_task, name="Up for grabs", claimable=True,
            cadence_days=3, last_done_at=ago(10),
        )
        _task(
            db, make_task, name="Soon", assignee_id=link.id,
            cadence_days=10, last_done_at=ago(1),  # due at day 5 -> in 4 days
        )
        _task(
            db, make_task, name="Weekly done", assignee_id=link.id,
            cadence_days=7, last_done_at=datetime.now(timezone.utc),
        )
        _task(
            db, make_task, name="Far off", assignee_id=link.id,
            cadence_days=60, last_done_at=ago(1),  # due in ~29 days
        )
        _task(
            db, make_task, name="Big project", assignee_id=link.id,
            task_type="project", cadence_days=30, last_done_at=ago(1),
        )
        _task(db, make_task, name="Zelda's", assignee_id=other_kid.id, last_done_at=ago(30))
        _task(db, make_task, name="Owner's open task", last_done_at=ago(30))  # not claimable
        _task(
            db, make_task, name="Retired", assignee_id=link.id,
            is_active=False, last_done_at=ago(30),
        )
        db.commit()

        body = _board(client, link)
        today = _by_name(body["today"])
        upcoming = _by_name(body["upcoming"])
        recurring = _by_name(body["recurring"])

        assert set(today) == {"Empty dishwasher", "Up for grabs"}
        d = today["Empty dishwasher"]
        assert d == {
            "id": str(dishes.id), "name": "Empty dishwasher", "room": "Kitchen",
            "instructions": "Plates go on the left", "estimated_minutes": 5,
            "effort": "quick", "cadence_days": 1, "cadence_label": "every day",
            "preferred_day": 0, "due_on": utc_today().isoformat(), "done": False,
            "completion_id": None, "completed_at": None, "can_undo": False,
            "claimable": False, "assigned_to_member": True,
        }
        grabs = today["Up for grabs"]
        assert grabs["claimable"] is True and grabs["assigned_to_member"] is False
        assert grabs["cadence_label"] == "every 3 days"

        assert set(upcoming) == {"Soon", "Weekly done"}
        assert upcoming["Soon"]["due_on"] == (utc_today() + timedelta(days=4)).isoformat()
        next_monday = utc_today() + timedelta(days=7 - utc_today().weekday())
        assert upcoming["Weekly done"]["due_on"] == next_monday.isoformat()
        assert upcoming["Weekly done"]["cadence_label"] == "every week"
        # sorted by due date
        dues = [c["due_on"] for c in body["upcoming"]]
        assert dues == sorted(dues)

        assert set(recurring) == {
            "Empty dishwasher", "Up for grabs", "Soon", "Weekly done", "Far off",
        }  # projects aren't recurring; others' and inactive chores never show
        assert recurring["Far off"]["due_on"] == (utc_today() + timedelta(days=29)).isoformat()
        assert recurring["Empty dishwasher"]["due_on"] == utc_today().isoformat()

    def test_stats(self, client, db, make_task, owner, link):
        link.current_streak = 4
        link.longest_streak = 12
        a = _task(db, make_task, name="A", assignee_id=link.id, last_done_at=ago(10))
        b = _task(db, make_task, name="B", assignee_id=link.id, last_done_at=ago(10))
        now = datetime.now(timezone.utc)
        db.add_all([
            CompletionLog(task_id=a.id, completed_by=link.id, completed_at=now, source="direct"),
            CompletionLog(task_id=b.id, completed_by=link.id, completed_at=now, source="orbit"),
            CompletionLog(task_id=a.id, completed_by=link.id, completed_at=ago(8), source="direct"),
            CompletionLog(task_id=a.id, completed_by=owner.id, completed_at=now, source="direct"),
        ])
        db.commit()
        stats = _board(client, link)["stats"]
        assert stats["current_streak"] == 4
        assert stats["longest_streak"] == 12
        assert stats["completed_today"] == 2  # the owner's and last week's don't count
        assert stats["completed_this_week"] == 2


# ---------------------------------------------------------------------------
# POST /complete + POST /undo (the round trip)
# ---------------------------------------------------------------------------

class TestCompleteUndo:
    def test_round_trip(self, client, db, make_task, owner, link):
        chore = _task(
            db, make_task, name="Feed the cat", assignee_id=link.id,
            cadence_days=1, last_done_at=ago(2),
        )
        original = chore.last_done_at
        db.commit()

        r = client.post(
            "/api/orbit/complete", headers=AUTH,
            json={"task_id": str(chore.id), "member_id": str(link.id)},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        completion_id = body["completion_id"]
        assert set(body) == {"completion_id", "completed_at"}
        assert datetime.fromisoformat(body["completed_at"]).tzinfo is not None

        log = db.get(CompletionLog, int(completion_id))
        assert log.source == "orbit"
        assert log.completed_by == link.id
        db.refresh(chore)
        db.refresh(link)
        assert chore.last_done_at is not None
        assert link.current_streak == 1  # the shared completion path ran

        entry = _by_name(_board(client, link)["today"])["Feed the cat"]
        assert entry["done"] is True
        assert entry["completion_id"] == completion_id
        assert entry["completed_at"] is not None
        assert entry["can_undo"] is True

        hist = client.get(
            f"/api/orbit/completions?member={link.id}", headers=AUTH
        ).json()["completions"]
        assert hist[0]["completion_id"] == completion_id
        assert hist[0]["source"] == "orbit"

        r = client.post(
            "/api/orbit/undo", headers=AUTH,
            json={"completion_id": completion_id, "member_id": str(link.id)},
        )
        assert r.status_code == 204
        assert db.get(CompletionLog, int(completion_id)) is None
        db.refresh(chore)
        assert scheduling._aware(chore.last_done_at) == scheduling._aware(original)

        entry = _by_name(_board(client, link)["today"])["Feed the cat"]
        assert entry["done"] is False and entry["completion_id"] is None

    def test_numeric_ids_are_accepted(self, client, db, make_task, owner, link):
        chore = _task(db, make_task, name="Trash", assignee_id=link.id, last_done_at=ago(10))
        db.commit()
        r = client.post(
            "/api/orbit/complete", headers=AUTH,
            json={"task_id": chore.id, "member_id": link.id},
        )
        assert r.status_code == 200

    def test_claimable_chore_can_be_completed(self, client, db, make_task, owner, link):
        chore = _task(db, make_task, name="Open", claimable=True, last_done_at=ago(10))
        db.commit()
        r = client.post(
            "/api/orbit/complete", headers=AUTH,
            json={"task_id": str(chore.id), "member_id": str(link.id)},
        )
        assert r.status_code == 200

    def test_someone_elses_chore_is_403(self, client, db, make_task, owner, link):
        other = User(name="Zelda", password_hash="x", role="kid")
        db.add(other)
        db.flush()
        chore = _task(db, make_task, name="Hers", assignee_id=other.id, last_done_at=ago(10))
        db.commit()
        r = client.post(
            "/api/orbit/complete", headers=AUTH,
            json={"task_id": str(chore.id), "member_id": str(link.id)},
        )
        assert r.status_code == 403
        assert "Link" in r.json()["detail"]
        assert db.query(CompletionLog).count() == 0

    def test_unknown_task_or_member_is_404(self, client, db, make_task, owner, link):
        chore = _task(db, make_task, name="Mine", assignee_id=link.id, last_done_at=ago(10))
        db.commit()
        for payload in (
            {"task_id": "999", "member_id": str(link.id)},
            {"task_id": "abc", "member_id": str(link.id)},
            {"task_id": str(chore.id), "member_id": "999"},
        ):
            r = client.post("/api/orbit/complete", headers=AUTH, json=payload)
            assert r.status_code == 404, payload

    def test_undo_out_of_window_is_409(self, client, db, make_task, owner, link):
        chore = _task(db, make_task, name="Old", assignee_id=link.id, last_done_at=ago(14))
        log = CompletionLog(
            task_id=chore.id, completed_by=link.id, completed_at=ago(1),
            source="orbit", previous_last_done_at=ago(14),
        )
        db.add(log)
        db.commit()
        r = client.post(
            "/api/orbit/undo", headers=AUTH,
            json={"completion_id": str(log.id), "member_id": str(link.id)},
        )
        assert r.status_code == 409
        assert "previous day" in r.json()["detail"]

    def test_undo_not_latest_is_409_and_can_undo_false(self, client, db, make_task, owner, link):
        chore = _task(db, make_task, name="Twice", assignee_id=link.id, last_done_at=ago(14))
        first = scheduling.complete_task(db, chore, link, "orbit", now=ago(0.001))
        second = scheduling.complete_task(db, chore, owner, "direct")
        db.commit()
        entry = _by_name(_board(client, link)["today"])["Twice"]
        assert entry["completion_id"] == str(first.id)
        assert entry["can_undo"] is False  # a newer completion stands
        r = client.post(
            "/api/orbit/undo", headers=AUTH,
            json={"completion_id": str(first.id), "member_id": str(link.id)},
        )
        assert r.status_code == 409
        assert second.id is not None

    def test_undo_someone_elses_completion_is_403(self, client, db, make_task, owner, link):
        chore = _task(db, make_task, name="Owner did it", last_done_at=ago(14))
        log = scheduling.complete_task(db, chore, owner, "direct")
        db.commit()
        r = client.post(
            "/api/orbit/undo", headers=AUTH,
            json={"completion_id": str(log.id), "member_id": str(link.id)},
        )
        assert r.status_code == 403

    def test_undo_unknown_is_404(self, client, db, owner, link):
        db.commit()
        r = client.post(
            "/api/orbit/undo", headers=AUTH,
            json={"completion_id": "999", "member_id": str(link.id)},
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /completions
# ---------------------------------------------------------------------------

class TestCompletions:
    def test_date_range_filter_newest_first(self, client, db, make_task, owner, link):
        kitchen = _room(db, "Kitchen")
        chore = _task(db, make_task, name="Sweep", assignee_id=link.id, room_id=kitchen.id)
        today = utc_today()

        def at(day_offset, hour):
            d = today - timedelta(days=day_offset)
            return datetime(d.year, d.month, d.day, hour, tzinfo=timezone.utc)

        logs = {
            key: CompletionLog(task_id=chore.id, completed_by=link.id, completed_at=when, source=src)
            for key, when, src in [
                ("too_old", at(10, 12), "direct"),
                ("start_day", at(5, 0), "hearth"),
                ("middle", at(3, 9), "orbit"),
                ("end_day", at(2, 23), "direct"),
                ("too_new", at(1, 0), "orbit"),
            ]
        }
        db.add_all(logs.values())
        db.add(CompletionLog(task_id=chore.id, completed_by=owner.id, completed_at=at(3, 10), source="direct"))
        db.commit()

        start = (today - timedelta(days=5)).isoformat()
        end = (today - timedelta(days=2)).isoformat()
        r = client.get(
            f"/api/orbit/completions?member={link.id}&start={start}&end={end}", headers=AUTH
        )
        assert r.status_code == 200
        items = r.json()["completions"]
        assert [c["completion_id"] for c in items] == [
            str(logs["end_day"].id), str(logs["middle"].id), str(logs["start_day"].id),
        ]
        assert items[1] == {
            "completion_id": str(logs["middle"].id), "task_id": str(chore.id),
            "task_name": "Sweep", "room": "Kitchen",
            "completed_at": items[1]["completed_at"], "source": "orbit",
        }
        assert datetime.fromisoformat(items[1]["completed_at"]) == at(3, 9)

    def test_92_day_cap(self, client, db, owner, link):
        db.commit()
        base = f"/api/orbit/completions?member={link.id}"
        assert client.get(f"{base}&start=2026-01-01&end=2026-04-02", headers=AUTH).status_code == 200  # 92 days
        assert client.get(f"{base}&start=2026-01-01&end=2026-04-03", headers=AUTH).status_code == 422  # 93 days

    def test_end_before_start_is_422(self, client, db, owner, link):
        db.commit()
        r = client.get(
            f"/api/orbit/completions?member={link.id}&start=2026-05-02&end=2026-05-01",
            headers=AUTH,
        )
        assert r.status_code == 422

    def test_bad_date_is_422(self, client, db, owner, link):
        db.commit()
        r = client.get(
            f"/api/orbit/completions?member={link.id}&start=nope&end=2026-05-01",
            headers=AUTH,
        )
        assert r.status_code == 422

    def test_unknown_member_is_404(self, client, db, owner):
        db.commit()
        r = client.get(
            "/api/orbit/completions?member=999&start=2026-05-01&end=2026-05-02", headers=AUTH
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Pure helpers (SPEC §4: decay-engine changes need tests)
# ---------------------------------------------------------------------------

class TestChoreDueAt:
    # A Wednesday, so "this week" started Monday 2026-07-27.
    NOW = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)

    def test_never_done_is_due_now(self, make_task):
        assert scheduling.chore_due_at(make_task(cadence_days=3), self.NOW) == self.NOW

    def test_already_aging_is_due_now(self, make_task):
        task = make_task(cadence_days=4, last_done_at=self.NOW - timedelta(days=3))
        assert scheduling.chore_due_at(task, self.NOW) == self.NOW

    def test_decay_chore_due_at_freshness_gate(self, make_task):
        done = self.NOW - timedelta(days=1)
        task = make_task(cadence_days=10, last_done_at=done)
        assert scheduling.chore_due_at(task, self.NOW) == done + timedelta(days=5)

    def test_weekly_chore_done_this_week_is_due_next_monday(self, make_task):
        task = make_task(cadence_days=7, last_done_at=self.NOW - timedelta(days=1))
        assert scheduling.chore_due_at(task, self.NOW) == datetime(
            2026, 8, 3, tzinfo=timezone.utc
        )

    def test_weekly_monday_is_local(self, make_task):
        chicago = ZoneInfo("America/Chicago")
        task = make_task(cadence_days=7, last_done_at=self.NOW - timedelta(hours=1))
        due = scheduling.chore_due_at(task, self.NOW, chicago)
        assert due.astimezone(chicago).replace(tzinfo=None) == datetime(2026, 8, 3)

    def test_snooze_pushes_it_out(self, make_task):
        until = self.NOW + timedelta(days=2)
        task = make_task(
            cadence_days=3, last_done_at=self.NOW - timedelta(days=10), snoozed_until=until
        )
        assert scheduling.chore_due_at(task, self.NOW) == until


class TestCheckUndoable:
    def test_mirrors_undo_guards(self, db, make_task, owner):
        task = _task(db, make_task, last_done_at=ago(14))
        old = CompletionLog(
            task_id=task.id, completed_by=owner.id, completed_at=ago(2), source="direct"
        )
        db.add(old)
        db.flush()
        with pytest.raises(scheduling.UndoWindowClosed):
            scheduling.check_undoable(db, old)
        first = scheduling.complete_task(db, task, owner, "orbit", now=ago(0.001))
        latest = scheduling.complete_task(db, task, owner, "orbit")
        with pytest.raises(scheduling.UndoNotLatest):
            scheduling.check_undoable(db, first)
        assert scheduling.check_undoable(db, latest) is None
        # read-only: nothing was deleted or rewound
        assert db.get(CompletionLog, first.id) is not None


@pytest.mark.parametrize(
    "days,label",
    [(1, "every day"), (7, "every week"), (14, "every 2 weeks"), (3, "every 3 days"),
     (30, "every month"), (365, "every year"), (None, None)],
)
def test_cadence_label(days, label):
    assert orbit_service.cadence_label(days) == label
