"""The parent check (services/parent_check.py, routers/checks.py).

A task with `needs_check` on turns a kid's Done into "ready to check";
an adult then marks it "checked" (physically inspected) or sends it back
(due again, with a note). Covered here:

- the round trips: ready -> checked, and ready -> sent back -> done again;
- permissions: only adults check, send back or undo a check;
- the decay rule: decay resets at "ready" (when the work happened);
  "checked" moves nothing; a send-back restores the previous state;
- default off: tasks without the setting complete exactly as before;
- undo: a kid's mis-tapped "ready" undoes like any completion, a checked
  one can't be undone from under the parent, and checks themselves undo;
- the surfaces: chores, Done Today, the Hearth wall;
- the ChatGPT tools, including that a kid's connection can't mark checked.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings as app_settings
from app.database import get_db
from app.main import app
from app.models import CompletionLog, Task, User
from app.services import completion, mcp_tools, parent_check, scheduling
from app.services.auth_service import SESSION_COOKIE_NAME, create_session_token

HEARTH_TOKEN = "test-token"
HEARTH = {"Authorization": f"Bearer {HEARTH_TOKEN}"}


def ago(days: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@pytest.fixture()
def client(db, monkeypatch):
    monkeypatch.setattr(app_settings, "hearth_device_token", HEARTH_TOKEN)
    monkeypatch.setattr(app_settings, "mcp_enabled", True)
    monkeypatch.setattr(app_settings, "mealgenie_api_url", "")
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def as_user(client: TestClient, user: User) -> TestClient:
    client.cookies.set(SESSION_COOKIE_NAME, create_session_token(user.id))
    return client


@pytest.fixture()
def chore(db, make_task, kid):
    """A weekly-ish chore assigned to the kid, due (last done 10 days ago),
    with the parent check turned on."""
    task = make_task(
        name="Tidy bedroom",
        cadence_days=5,
        last_done_at=ago(10),
        assignee_id=kid.id,
        needs_check=True,
    )
    db.add(task)
    db.commit()
    return task


def _ready(client, kid, task) -> dict:
    """The kid taps Done on a needs_check chore."""
    r = as_user(client, kid).post(f"/api/tasks/{task.id}/complete", json={"source": "direct"})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Round trips
# ---------------------------------------------------------------------------

class TestRoundTrips:
    def test_ready_then_checked(self, client, db, owner, kid, chore):
        done = _ready(client, kid, chore)
        assert done["check_status"] == "ready"
        assert done["check_completion_id"] == done["completion_id"]
        assert done["band"] == "fresh"  # decay reset at "ready"

        waiting = as_user(client, owner).get("/api/checks").json()["waiting"]
        assert [w["task_name"] for w in waiting] == ["Tidy bedroom"]
        assert waiting[0]["done_by_name"] == "Sam"
        assert waiting[0]["status"] == "ready"

        db.refresh(chore)
        reset_at = chore.last_done_at
        r = client.post(f"/api/checks/{done['completion_id']}/checked")
        assert r.status_code == 200, r.text
        item = r.json()
        assert item["status"] == "checked"
        assert item["checked_by_id"] == owner.id
        assert item["checked_by_name"] == "Maryann"
        assert item["checked_at"] is not None

        db.refresh(chore)
        assert chore.last_done_at == reset_at  # "checked" moves nothing
        assert client.get("/api/checks").json()["waiting"] == []
        entry = client.get("/api/done-today").json()["completions"][0]
        assert entry["check_status"] == "checked"
        assert entry["checked_by_name"] == "Maryann"

    def test_ready_then_sent_back_then_done_again(self, client, db, owner, kid, chore):
        before = _aware(chore.last_done_at)
        done = _ready(client, kid, chore)

        r = as_user(client, owner).post(
            f"/api/checks/{done['completion_id']}/send-back",
            json={"note": "  The bed still needs making.  "},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "sent_back"
        assert r.json()["note"] == "The bed still needs making."

        db.refresh(chore)
        assert _aware(chore.last_done_at) == before  # due again, true history
        assert client.get("/api/checks").json()["waiting"] == []
        # Not a ta-da: a sent-back completion isn't done.
        assert client.get("/api/done-today").json()["completions"] == []

        chores = as_user(client, kid).get("/api/chores").json()
        [mine] = chores["mine"]
        assert mine["check_status"] == "sent_back"
        assert mine["check_note"] == "The bed still needs making."
        assert chores["waiting_for_check"] == []

        again = _ready(client, kid, chore)
        assert again["completion_id"] != done["completion_id"]
        assert again["check_status"] == "ready"
        chores = client.get("/api/chores").json()
        assert chores["mine"] == []
        [waiting] = chores["waiting_for_check"]
        assert waiting["check_status"] == "ready"
        assert waiting["check_note"] is None

        r = as_user(client, owner).post(f"/api/checks/{again['completion_id']}/checked")
        assert r.json()["status"] == "checked"


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

class TestPermissions:
    def test_kid_cannot_check_send_back_undo_or_list(self, client, db, owner, kid, chore):
        done = _ready(client, kid, chore)
        cid = done["completion_id"]
        assert client.get("/api/checks").status_code == 403
        assert client.post(f"/api/checks/{cid}/checked").status_code == 403
        assert client.post(f"/api/checks/{cid}/send-back", json={}).status_code == 403
        assert client.post(f"/api/checks/{cid}/undo").status_code == 403
        log = db.get(CompletionLog, cid)
        db.refresh(log)
        assert log.check_status == "ready"
        assert log.checked_by is None

    def test_service_refuses_a_kid_too(self, db, make_task, owner, kid):
        task = make_task(needs_check=True, last_done_at=ago(10), assignee_id=kid.id)
        db.add(task)
        db.flush()
        log = scheduling.complete_task(db, task, kid, "direct", check_status="ready")
        with pytest.raises(parent_check.NotAParent):
            parent_check.mark_checked(db, log, kid)
        with pytest.raises(parent_check.NotAParent):
            parent_check.send_back(db, log, kid)

    def test_kid_cannot_ready_someone_elses_chore(self, client, db, make_task, owner, kid):
        task = make_task(needs_check=True, last_done_at=ago(10), assignee_id=owner.id)
        db.add(task)
        db.commit()
        r = as_user(client, kid).post(f"/api/tasks/{task.id}/ready-for-check", json={})
        assert r.status_code == 403

    def test_cannot_check_twice_into_send_back(self, client, db, owner, kid, chore):
        done = _ready(client, kid, chore)
        cid = done["completion_id"]
        as_user(client, owner)
        assert client.post(f"/api/checks/{cid}/checked").status_code == 200
        assert client.post(f"/api/checks/{cid}/checked").status_code == 200  # idempotent
        assert client.post(f"/api/checks/{cid}/send-back", json={}).status_code == 409

    def test_plain_completion_cannot_be_checked(self, client, db, make_task, owner):
        task = make_task(last_done_at=ago(10))
        db.add(task)
        db.commit()
        cid = as_user(client, owner).post(
            f"/api/tasks/{task.id}/complete", json={}
        ).json()["completion_id"]
        assert client.post(f"/api/checks/{cid}/checked").status_code == 409


# ---------------------------------------------------------------------------
# Default off, and who triggers it
# ---------------------------------------------------------------------------

class TestDefaultOff:
    def test_new_tasks_default_off_and_complete_as_before(self, client, db, owner, kid):
        r = as_user(client, owner).post(
            "/api/tasks",
            json={"name": "Feed cat", "cadence_days": 1, "estimated_minutes": 5, "assignee_id": kid.id},
        )
        assert r.status_code == 201
        assert r.json()["needs_check"] is False
        done = as_user(client, kid).post(f"/api/tasks/{r.json()['id']}/complete", json={}).json()
        assert done["check_status"] is None
        log = db.get(CompletionLog, done["completion_id"])
        assert log.check_status is None
        assert as_user(client, owner).get("/api/checks").json()["waiting"] == []

    def test_setting_on_create_and_update(self, client, db, owner):
        as_user(client, owner)
        task = client.post(
            "/api/tasks",
            json={"name": "Dishes", "cadence_days": 1, "estimated_minutes": 10, "needs_check": True},
        ).json()
        assert task["needs_check"] is True
        assert client.patch(f"/api/tasks/{task['id']}", json={"needs_check": False}).json()["needs_check"] is False
        assert client.patch(f"/api/tasks/{task['id']}", json={"name": "Dishes!"}).json()["needs_check"] is False

    def test_adults_own_done_on_a_needs_check_task_is_plain(self, client, db, owner, chore):
        done = as_user(client, owner).post(f"/api/tasks/{chore.id}/complete", json={}).json()
        assert done["check_status"] is None

    def test_adult_can_ask_for_a_check_explicitly(self, client, db, owner, make_task):
        task = make_task(last_done_at=ago(10))
        db.add(task)
        db.commit()
        done = as_user(client, owner).post(f"/api/tasks/{task.id}/ready-for-check", json={}).json()
        assert done["check_status"] == "ready"

    def test_ready_twice_returns_the_same_completion(self, client, db, kid, chore):
        first = _ready(client, kid, chore)
        second = client.post(f"/api/tasks/{chore.id}/ready-for-check", json={}).json()
        assert second["completion_id"] == first["completion_id"]
        rows = db.scalars(select(CompletionLog).where(CompletionLog.task_id == chore.id)).all()
        assert len(rows) == 1

    def test_kid_ready_notifies_the_parent(self, client, db, owner, kid, chore, monkeypatch):
        sent = []
        monkeypatch.setattr(completion, "notify_owners", lambda db, title, body: sent.append((title, body)))
        _ready(client, kid, chore)
        assert sent and sent[0][0].startswith("Ready for a check")

    def test_send_back_pushes_the_kid(self, client, db, owner, kid, chore, monkeypatch):
        sent = []
        monkeypatch.setattr(
            completion, "push_to_user", lambda db, uid, title, body: sent.append((uid, body))
        )
        cid = _ready(client, kid, chore)["completion_id"]
        as_user(client, owner).post(f"/api/checks/{cid}/send-back", json={"note": "Under the bed too"})
        assert sent == [(kid.id, "Maryann sent back Tidy bedroom for another go. “Under the bed too”")]


# ---------------------------------------------------------------------------
# Decay
# ---------------------------------------------------------------------------

NOW = datetime(2026, 11, 15, 18, 0, tzinfo=timezone.utc)  # a Sunday


class TestDecay:
    def _task(self, db, make_task, kid, **overrides):
        fields = dict(cadence_days=7, last_done_at=NOW - timedelta(days=8), assignee_id=kid.id, needs_check=True)
        fields.update(overrides)
        task = make_task(**fields)
        db.add(task)
        db.flush()
        return task

    def test_ready_resets_decay_to_zero(self, db, make_task, owner, kid):
        task = self._task(db, make_task, kid, cadence_days=3)
        scheduling.complete_task(db, task, kid, "direct", NOW, check_status="ready")
        assert scheduling.dirtiness_ratio(task, NOW) == 0

    def test_checking_later_does_not_move_the_schedule(self, db, make_task, owner, kid):
        """Done Sunday, checked Tuesday: the chore was done Sunday."""
        task = self._task(db, make_task, kid, cadence_days=3)
        log = scheduling.complete_task(db, task, kid, "direct", NOW, check_status="ready")
        parent_check.mark_checked(db, log, owner, now=NOW + timedelta(days=2))
        assert _aware(task.last_done_at) == NOW
        assert _aware(log.checked_at) == NOW + timedelta(days=2)

    def test_weekly_chore_done_sunday_checked_monday_stays_last_week(self, db, make_task, owner, kid):
        task = self._task(db, make_task, kid)
        log = scheduling.complete_task(db, task, kid, "direct", NOW, check_status="ready")
        monday = NOW + timedelta(days=1)
        parent_check.mark_checked(db, log, owner, now=monday)
        db.flush()
        mine, _ = scheduling.chores_for_user(db, kid.id, now=monday)
        assert task in mine  # new week, due again: the check didn't count as this week's

    def test_send_back_restores_the_exact_previous_ratio(self, db, make_task, owner, kid):
        task = self._task(db, make_task, kid, cadence_days=5)
        before = scheduling.dirtiness_ratio(task, NOW)
        log = scheduling.complete_task(db, task, kid, "direct", NOW, check_status="ready")
        parent_check.send_back(db, log, owner, "again please", now=NOW)
        assert scheduling.dirtiness_ratio(task, NOW) == before
        mine, _ = scheduling.chores_for_user(db, kid.id, now=NOW)
        assert task in mine

    def test_send_back_of_a_first_ever_completion_is_never_done_again(self, db, make_task, owner, kid):
        task = self._task(db, make_task, kid, last_done_at=None)
        log = scheduling.complete_task(db, task, kid, "direct", NOW, check_status="ready")
        parent_check.send_back(db, log, owner, now=NOW)
        assert task.last_done_at is None

    def test_send_back_refused_after_a_newer_completion(self, db, make_task, owner, kid):
        task = self._task(db, make_task, kid)
        log = scheduling.complete_task(db, task, kid, "direct", NOW, check_status="ready")
        scheduling.complete_task(db, task, owner, "direct", NOW + timedelta(hours=1))
        with pytest.raises(parent_check.CheckRefused):
            parent_check.send_back(db, log, owner, now=NOW + timedelta(hours=2))
        assert _aware(task.last_done_at) == NOW + timedelta(hours=1)
        assert parent_check.waiting_for_check(db) == []  # superseded, no longer waiting


# ---------------------------------------------------------------------------
# Undo
# ---------------------------------------------------------------------------

class TestUndo:
    def test_kid_can_undo_a_mistapped_ready(self, client, db, owner, kid, chore):
        before = _aware(chore.last_done_at)
        cid = _ready(client, kid, chore)["completion_id"]
        assert client.post(f"/api/completions/{cid}/undo").status_code == 200
        db.refresh(chore)
        assert _aware(chore.last_done_at) == before
        assert db.get(CompletionLog, cid) is None

    def test_checked_completion_cannot_be_undone_from_under_the_parent(self, client, db, owner, kid, chore):
        cid = _ready(client, kid, chore)["completion_id"]
        as_user(client, owner).post(f"/api/checks/{cid}/checked")
        r = as_user(client, kid).post(f"/api/completions/{cid}/undo")
        assert r.status_code == 409
        assert "undo the check first" in r.json()["detail"]

    def test_undo_checked_goes_back_to_ready(self, client, db, owner, kid, chore):
        cid = _ready(client, kid, chore)["completion_id"]
        as_user(client, owner).post(f"/api/checks/{cid}/checked")
        r = client.post(f"/api/checks/{cid}/undo")
        assert r.status_code == 200
        assert r.json()["status"] == "ready"
        assert r.json()["checked_by_id"] is None
        assert [w["completion_id"] for w in client.get("/api/checks").json()["waiting"]] == [cid]

    def test_undo_send_back_reapplies_the_reset(self, client, db, owner, kid, chore):
        cid = _ready(client, kid, chore)["completion_id"]
        done_at = _aware(db.get(CompletionLog, cid).completed_at)
        as_user(client, owner).post(f"/api/checks/{cid}/send-back", json={"note": "x"})
        r = client.post(f"/api/checks/{cid}/undo")
        assert r.status_code == 200
        assert r.json()["status"] == "ready"
        assert r.json()["note"] is None
        db.refresh(chore)
        assert _aware(chore.last_done_at) == done_at

    def test_undo_send_back_refused_once_redone(self, client, db, owner, kid, chore):
        cid = _ready(client, kid, chore)["completion_id"]
        as_user(client, owner).post(f"/api/checks/{cid}/send-back", json={})
        _ready(client, kid, chore)
        assert as_user(client, owner).post(f"/api/checks/{cid}/undo").status_code == 409

    def test_nothing_to_undo_is_409(self, client, db, owner, kid, chore):
        cid = _ready(client, kid, chore)["completion_id"]
        assert as_user(client, owner).post(f"/api/checks/{cid}/undo").status_code == 409


# ---------------------------------------------------------------------------
# The Hearth wall
# ---------------------------------------------------------------------------

class TestHearth:
    def test_wall_completion_by_a_kid_waits_for_a_check(self, client, db, owner, kid, chore):
        r = client.post(
            "/api/hearth/complete",
            json={"taskId": str(chore.id), "memberId": str(kid.id)},
            headers=HEARTH,
        )
        assert r.status_code == 200
        assert r.json()["checkStatus"] == "ready"
        [board] = client.get("/api/hearth/kids", headers=HEARTH).json()["kids"]
        [entry] = board["chores"]
        assert entry["done"] is True
        assert entry["completionId"] == r.json()["completionId"]
        assert entry["checkStatus"] == "ready"

    def test_sent_back_shows_outstanding_on_the_wall(self, client, db, owner, kid, chore):
        cid = _ready(client, kid, chore)["completion_id"]
        as_user(client, owner).post(f"/api/checks/{cid}/send-back", json={})
        [board] = client.get("/api/hearth/kids", headers=HEARTH).json()["kids"]
        [entry] = board["chores"]
        assert entry["done"] is False
        assert entry["completionId"] is None
        assert entry["checkStatus"] == "sent_back"
        done = client.get(f"/api/hearth/done-today?member={kid.id}", headers=HEARTH).json()
        assert done["completions"] == []

    def test_existing_shapes_unchanged_for_plain_chores(self, client, db, make_task, owner, kid):
        task = make_task(last_done_at=ago(10), assignee_id=kid.id)
        db.add(task)
        db.commit()
        r = client.post(
            "/api/hearth/complete",
            json={"taskId": str(task.id), "memberId": str(kid.id)},
            headers=HEARTH,
        )
        assert set(r.json()) == {"completionId", "checkStatus"}
        assert r.json()["checkStatus"] is None
        [board] = client.get("/api/hearth/kids", headers=HEARTH).json()["kids"]
        assert set(board["chores"][0]) == {"id", "name", "done", "completionId", "checkStatus"}


# ---------------------------------------------------------------------------
# The ChatGPT tools
# ---------------------------------------------------------------------------

def _token(db, user):
    from tests.test_mcp_tools import _token_for

    return _token_for(db, user)


def _call(client, token, name, arguments=None):
    from tests.test_mcp_tools import call

    client.cookies.clear()
    return call(client, token, name, arguments)


class TestMcpTools:
    def test_tool_definitions(self):
        tools = mcp_tools.TOOLS_BY_NAME
        for name in ("list_waiting_for_check", "mark_ready_for_check", "mark_checked", "send_back", "undo_check"):
            assert name in tools
        checked = tools["mark_checked"].definition()
        assert "PHYSICALLY INSPECTED" in checked["description"]
        assert "guess" in checked["description"]
        send_back = tools["send_back"].definition()["annotations"]
        assert send_back["destructiveHint"] is False
        assert send_back["idempotentHint"] is False
        assert send_back["readOnlyHint"] is False
        assert tools["list_waiting_for_check"].definition()["annotations"]["readOnlyHint"] is True
        for name in ("create_task", "update_task"):
            assert "needs_check" in tools[name].properties

    def test_kid_marks_ready_but_cannot_mark_checked(self, client, db, owner, kid, chore):
        kid_token = _token(db, kid)
        ready = _call(client, kid_token, "mark_ready_for_check", {"task_id": chore.id})
        assert not ready["isError"], ready
        cid = ready["structuredContent"]["completion_id"]
        assert ready["structuredContent"]["check_status"] == "ready"

        refused = _call(client, kid_token, "mark_checked", {"completion_id": cid})
        assert refused["isError"]
        assert "adult" in refused["content"][0]["text"]
        refused = _call(client, kid_token, "send_back", {"completion_id": cid, "note": "nah"})
        assert refused["isError"]
        assert db.get(CompletionLog, cid).check_status == "ready"

        mine = _call(client, kid_token, "get_my_chores")["structuredContent"]
        assert [t["id"] for t in mine["waiting_for_check"]] == [chore.id]

    def test_parent_lists_checks_and_sends_back(self, client, db, owner, kid, chore):
        _ready(client, kid, chore)
        owner_token = _token(db, owner)
        listed = _call(client, owner_token, "list_waiting_for_check")
        [item] = listed["structuredContent"]["waiting"]
        sent = _call(
            client, owner_token, "send_back", {"completion_id": item["completion_id"], "note": "Floor too"}
        )
        assert not sent["isError"], sent
        assert sent["structuredContent"]["status"] == "sent_back"
        undone = _call(client, owner_token, "undo_check", {"completion_id": item["completion_id"]})
        assert undone["structuredContent"]["status"] == "ready"
        checked = _call(client, owner_token, "mark_checked", {"completion_id": item["completion_id"]})
        assert checked["structuredContent"]["status"] == "checked"
        overview = _call(client, owner_token, "get_overview")["structuredContent"]
        assert overview["waiting_for_parent_check"] == []

    def test_setting_through_create_and_update_task(self, client, db, owner):
        owner_token = _token(db, owner)
        made = _call(
            client,
            owner_token,
            "create_task",
            {"name": "Make bed", "cadence_days": 1, "estimated_minutes": 3, "needs_check": True},
        )
        assert made["structuredContent"]["needs_check"] is True
        changed = _call(
            client, owner_token, "update_task", {"task_id": made["structuredContent"]["id"], "needs_check": False}
        )
        assert changed["structuredContent"]["needs_check"] is False
