"""Tests for the Hearth wall API (docs/hearth-integration.md).

Router-level tests drive the real FastAPI app through TestClient with the
in-memory SQLite session injected via a get_db override, plus a pure
service test for next_task_for_scope (SPEC §4: ranking changes need
tests). The device token is monkeypatched on the shared settings
singleton — the same object both the router dependency and
auth_service.verify_device_token read.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings as app_settings
from app.database import get_db
from app.main import app
from app.models import CompletionLog, Room, Setting, Task, User
from app.services import completion, scheduling

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def ago(days: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


@pytest.fixture()
def client(db, monkeypatch):
    """The real app, wired to the test session, with the integration
    configured (a non-empty device token)."""
    monkeypatch.setattr(app_settings, "hearth_device_token", TOKEN)
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _room(db, name, sort_order=0):
    room = Room(name=name, sort_order=sort_order)
    db.add(room)
    db.flush()
    return room


def _task(db, make_task, **overrides):
    task = make_task(**overrides)
    db.add(task)
    db.flush()
    return task


# ---------------------------------------------------------------------------
# Device auth (gap #1)
# ---------------------------------------------------------------------------

class TestDeviceAuth:
    def test_missing_header_is_401(self, client):
        assert client.get("/api/hearth/rooms").status_code == 401

    def test_wrong_token_is_401(self, client):
        r = client.get("/api/hearth/rooms", headers={"Authorization": "Bearer nope"})
        assert r.status_code == 401

    def test_non_bearer_is_401(self, client):
        r = client.get("/api/hearth/rooms", headers={"Authorization": TOKEN})
        assert r.status_code == 401

    def test_unconfigured_is_503(self, client, monkeypatch):
        # No token set anywhere = integration off, even with a bearer header.
        monkeypatch.setattr(app_settings, "hearth_device_token", "")
        r = client.get("/api/hearth/rooms", headers=AUTH)
        assert r.status_code == 503

    def test_valid_token_passes(self, client):
        assert client.get("/api/hearth/rooms", headers=AUTH).status_code == 200


# ---------------------------------------------------------------------------
# GET /rooms (gap #4)
# ---------------------------------------------------------------------------

def test_rooms_projected_to_string_ids(client, db):
    b = _room(db, "Bathroom", sort_order=2)
    k = _room(db, "Kitchen", sort_order=1)
    db.commit()
    rooms = client.get("/api/hearth/rooms", headers=AUTH).json()["rooms"]
    # ordered by sort_order; ids are stringified Tada ints
    assert rooms == [
        {"id": str(k.id), "name": "Kitchen"},
        {"id": str(b.id), "name": "Bathroom"},
    ]


# ---------------------------------------------------------------------------
# GET /next (gap #4, SPEC D4)
# ---------------------------------------------------------------------------

class TestNext:
    def test_returns_the_dirtiest_head_only(self, client, db, make_task, owner):
        kitchen = _room(db, "Kitchen")
        _task(db, make_task, name="Barely aging", cadence_days=7, last_done_at=ago(4))
        top = _task(
            db, make_task, name="Wipe counters", cadence_days=7,
            last_done_at=ago(14), room_id=kitchen.id,
        )
        db.commit()
        body = client.get(
            f"/api/hearth/next?member={owner.id}", headers=AUTH
        ).json()
        assert body["task"]["id"] == str(top.id)
        assert body["task"]["name"] == "Wipe counters"
        assert body["task"]["room"] == "Kitchen"
        # SPEC D4: id/name/room only — the decay score never crosses the wire.
        assert set(body["task"].keys()) == {"id", "name", "room"}

    def test_null_when_everything_is_fresh(self, client, db, make_task, owner):
        _task(db, make_task, last_done_at=ago(0), cadence_days=7)  # ratio ~0
        db.commit()
        assert client.get(
            f"/api/hearth/next?member={owner.id}", headers=AUTH
        ).json() == {"task": None}

    def test_room_scope_overrides_global_priority(self, client, db, make_task, owner):
        r1 = _room(db, "Kitchen")
        r2 = _room(db, "Garage")
        in_r1 = _task(db, make_task, name="R1", last_done_at=ago(8), room_id=r1.id)
        _task(db, make_task, name="R2 dirtier", last_done_at=ago(40), room_id=r2.id)
        db.commit()
        body = client.get(
            f"/api/hearth/next?member={owner.id}&room={r1.id}", headers=AUTH
        ).json()
        assert body["task"]["id"] == str(in_r1.id)

    def test_bad_room_is_400(self, client, db, owner):
        db.commit()
        r = client.get(
            f"/api/hearth/next?member={owner.id}&room=abc", headers=AUTH
        )
        assert r.status_code == 400

    def test_unknown_member_is_404(self, client, db):
        db.commit()
        assert client.get("/api/hearth/next?member=999", headers=AUTH).status_code == 404


# ---------------------------------------------------------------------------
# GET /done-today (gap #5)
# ---------------------------------------------------------------------------

def test_done_today_filters_to_one_member(client, db, make_task, owner, kid):
    mine = _task(db, make_task, name="Mine", last_done_at=ago(14))
    theirs = _task(db, make_task, name="Theirs", last_done_at=ago(14))
    scheduling.complete_task(db, mine, owner, "hearth")
    scheduling.complete_task(db, theirs, kid, "hearth")
    db.commit()

    names = [
        c["taskName"]
        for c in client.get(
            f"/api/hearth/done-today?member={owner.id}", headers=AUTH
        ).json()["completions"]
    ]
    assert names == ["Mine"]  # the kid's completion is filtered out


# ---------------------------------------------------------------------------
# GET /kids (gap #6)
# ---------------------------------------------------------------------------

class TestKids:
    def test_outstanding_and_completed(self, client, db, make_task, owner, kid):
        outstanding = _task(
            db, make_task, name="Make bed", assignee_id=kid.id, last_done_at=ago(14)
        )
        done = _task(
            db, make_task, name="Feed dog", assignee_id=kid.id, last_done_at=ago(14)
        )
        log = scheduling.complete_task(db, done, kid, "hearth")
        db.commit()

        kids = client.get("/api/hearth/kids", headers=AUTH).json()["kids"]
        assert len(kids) == 1
        chores = {c["name"]: c for c in kids[0]["chores"]}
        assert kids[0]["memberId"] == str(kid.id)
        assert chores["Make bed"]["done"] is False
        assert chores["Make bed"]["id"] == str(outstanding.id)
        assert "completionId" not in chores["Make bed"] or chores["Make bed"]["completionId"] is None
        assert chores["Feed dog"]["done"] is True
        assert chores["Feed dog"]["completionId"] == str(log.id)

    def test_completed_wins_over_re_aged_outstanding(self, client, db, make_task, owner, kid):
        # A chore that reads dirty (in `mine`) AND was completed today must
        # appear once, done — never as both outstanding and done.
        chore = _task(
            db, make_task, name="Tidy", assignee_id=kid.id,
            cadence_days=7, last_done_at=ago(5),  # ratio ~0.71 -> in `mine`
        )
        log = CompletionLog(
            task_id=chore.id, completed_by=kid.id,
            completed_at=datetime.now(timezone.utc), source="hearth",
        )
        db.add(log)
        db.commit()

        chores = client.get("/api/hearth/kids", headers=AUTH).json()["kids"][0]["chores"]
        tidy = [c for c in chores if c["name"] == "Tidy"]
        assert len(tidy) == 1
        assert tidy[0]["done"] is True


# ---------------------------------------------------------------------------
# POST /complete (gaps #2, #3)
# ---------------------------------------------------------------------------

class TestComplete:
    def test_attributes_to_member_with_hearth_source(self, client, db, make_task, owner, kid):
        task = _task(db, make_task, name="Sweep", assignee_id=kid.id, last_done_at=ago(14))
        db.commit()
        r = client.post(
            "/api/hearth/complete",
            headers=AUTH,
            json={"taskId": str(task.id), "memberId": str(kid.id), "source": "hearth"},
        )
        assert r.status_code == 200
        completion_id = int(r.json()["completionId"])
        log = db.get(CompletionLog, completion_id)
        assert log.completed_by == kid.id
        assert log.source == "hearth"
        assert task.last_done_at is not None  # decay curve reset

    def test_kid_completion_notifies_owner(self, client, db, make_task, owner, kid, monkeypatch):
        calls = []
        monkeypatch.setattr(
            completion, "notify_owners", lambda db, title, body: calls.append((title, body))
        )
        task = _task(db, make_task, name="Trash", assignee_id=kid.id, last_done_at=ago(14))
        db.commit()
        client.post(
            "/api/hearth/complete",
            headers=AUTH,
            json={"taskId": str(task.id), "memberId": str(kid.id)},
        )
        assert len(calls) == 1 and "Ta-da" in calls[0][0]

    def test_owner_completion_does_not_notify(self, client, db, make_task, owner, monkeypatch):
        calls = []
        monkeypatch.setattr(
            completion, "notify_owners", lambda db, title, body: calls.append(1)
        )
        task = _task(db, make_task, name="Mop", last_done_at=ago(14))
        db.commit()
        client.post(
            "/api/hearth/complete",
            headers=AUTH,
            json={"taskId": str(task.id), "memberId": str(owner.id)},
        )
        assert calls == []

    def test_kid_cannot_complete_someone_elses_task(self, client, db, make_task, owner, kid):
        other = User(name="Other Kid", password_hash="x", role="kid")
        db.add(other)
        db.flush()
        task = _task(db, make_task, name="Not yours", assignee_id=other.id, last_done_at=ago(14))
        db.commit()
        r = client.post(
            "/api/hearth/complete",
            headers=AUTH,
            json={"taskId": str(task.id), "memberId": str(kid.id)},
        )
        assert r.status_code == 403

    def test_unknown_task_is_404(self, client, db, owner):
        db.commit()
        r = client.post(
            "/api/hearth/complete",
            headers=AUTH,
            json={"taskId": "999", "memberId": str(owner.id)},
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /undo
# ---------------------------------------------------------------------------

class TestUndo:
    def test_reverses_todays_completion(self, client, db, make_task, owner):
        task = _task(db, make_task, name="Dishes", last_done_at=ago(14))
        original = task.last_done_at
        log = scheduling.complete_task(db, task, owner, "hearth")
        completion_id = log.id
        db.commit()
        r = client.post(
            "/api/hearth/undo",
            headers=AUTH,
            json={"completionId": str(completion_id), "memberId": str(owner.id)},
        )
        assert r.status_code == 204
        assert db.get(CompletionLog, completion_id) is None
        # SQLite returns naive UTC; _aware normalizes both to compare the instant.
        assert scheduling._aware(task.last_done_at) == scheduling._aware(original)

    def test_out_of_window_is_409(self, client, db, make_task, owner):
        task = _task(db, make_task, name="Old", last_done_at=ago(14))
        log = CompletionLog(
            task_id=task.id, completed_by=owner.id,
            completed_at=datetime.now(timezone.utc) - timedelta(days=1),
            source="hearth", previous_last_done_at=ago(14),
        )
        db.add(log)
        db.commit()
        r = client.post(
            "/api/hearth/undo",
            headers=AUTH,
            json={"completionId": str(log.id), "memberId": str(owner.id)},
        )
        assert r.status_code == 409

    def test_member_cannot_undo_another_members_completion(self, client, db, make_task, owner, kid):
        other = User(name="Other Kid", password_hash="x", role="kid")
        db.add(other)
        db.flush()
        task = _task(db, make_task, name="Theirs", last_done_at=ago(14))
        log = scheduling.complete_task(db, task, other, "hearth")
        db.commit()
        r = client.post(
            "/api/hearth/undo",
            headers=AUTH,
            json={"completionId": str(log.id), "memberId": str(kid.id)},
        )
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Service: next_task_for_scope (SPEC §4 — ranking changes need tests)
# ---------------------------------------------------------------------------

class TestNextTaskForScope:
    NOW = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)

    def test_returns_priority_head(self, db, make_task, owner):
        low = _task(db, make_task, name="Low", cadence_days=7,
                    last_done_at=self.NOW - timedelta(days=4))
        _ = low
        high = _task(db, make_task, name="High", cadence_days=7,
                     last_done_at=self.NOW - timedelta(days=20))
        head = scheduling.next_task_for_scope(
            db, for_user_id=owner.id, now=self.NOW
        )
        assert head is high

    def test_none_when_all_fresh(self, db, make_task, owner):
        _task(db, make_task, cadence_days=7, last_done_at=self.NOW - timedelta(hours=1))
        assert scheduling.next_task_for_scope(db, for_user_id=owner.id, now=self.NOW) is None
