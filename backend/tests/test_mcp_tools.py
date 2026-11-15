"""The ChatGPT connector's tools (services/mcp_tools.py, routers/mcp.py).

The coverage tests keep the promise "ChatGPT can do anything you can do
in Tada": every user-facing route has a tool (or a reason in LEFT_OUT),
and every tool points at a real route. The call tests run representative
tools through POST /api/mcp with a real access token — a read, writes, a
delete, a kid hitting an owner-only tool, and a validation error.
"""

import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import settings as app_settings
from app.database import get_db
from app.main import app
from app.models import Room, Setting, Supply, Task, User
from app.services import mcp_tools, oauth_service
from app.services.oauth_service import OAuthClient


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------

def _user_routes() -> set[tuple[str, str]]:
    """Every (METHOD, path) under /api/ the app serves, read from the
    OpenAPI document (independent of how FastAPI nests included routers)."""
    routes = set()
    for path, operations in app.openapi()["paths"].items():
        if not path.startswith("/api/") or path.startswith(mcp_tools.EXCLUDED_PREFIXES):
            continue
        for method in operations:
            routes.add((method.upper(), path))
    assert len(routes) > 40  # guard against a silently empty walk
    return routes


def test_every_user_route_has_a_tool():
    covered = {r for tool in mcp_tools.TOOLS for r in tool.covered_routes()}
    missing = _user_routes() - covered - set(mcp_tools.LEFT_OUT)
    assert not missing, f"Routes with no MCP tool (add one or list in LEFT_OUT): {sorted(missing)}"


def test_every_tool_points_at_a_real_route():
    real = _user_routes()
    for tool in mcp_tools.TOOLS:
        for route in tool.covered_routes():
            assert route in real, f"{tool.name} -> {route} is not a route"


def test_tool_definitions_are_well_formed():
    names = [t.name for t in mcp_tools.TOOLS]
    assert len(names) == len(set(names))
    for tool in mcp_tools.TOOLS:
        definition = tool.definition()
        assert re.fullmatch(r"[a-z][a-z0-9_]*", tool.name)
        assert 20 <= len(tool.description) <= 400, tool.name
        schema = definition["inputSchema"]
        for key in schema["required"]:
            assert key in schema["properties"], (tool.name, key)
        for param in re.findall(r"{(\w+)}", tool.path):
            assert param in schema["required"], (tool.name, param)
        for prop in schema["properties"].values():
            assert prop.get("description") or prop.get("type") == "array", tool.name
        hints = definition["annotations"]
        if tool.method == "DELETE":
            assert hints["destructiveHint"], tool.name
        if tool.method == "GET":
            assert hints["readOnlyHint"], tool.name


# ---------------------------------------------------------------------------
# Calls
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(db, monkeypatch):
    monkeypatch.setattr(app_settings, "mcp_enabled", True)
    monkeypatch.setattr(app_settings, "mealgenie_api_url", "")
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _token_for(db, user: User) -> str:
    """An access token as if the OAuth flow had run for `user`."""
    client = db.get(OAuthClient, "test-client")
    if client is None:
        db.add(
            OAuthClient(
                client_id="test-client",
                redirect_uris='["http://localhost/cb"]',
                token_endpoint_auth_method="none",
                grant_types='["authorization_code","refresh_token"]',
                created_at=datetime.now(timezone.utc),
            )
        )
    value = oauth_service.new_secret()
    db.add(
        oauth_service.OAuthToken(
            token_hash=oauth_service.hash_secret(value),
            kind="access",
            client_id="test-client",
            user_id=user.id,
            scope="mcp",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    return value


def call(client, token, name, arguments=None) -> dict:
    response = client.post(
        "/api/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    return response.json()["result"]


@pytest.fixture()
def owner_token(db, owner):
    db.commit()
    return _token_for(db, owner)


def test_read_list_tasks_with_filters(client, db, owner_token):
    room = Room(name="Kitchen", sort_order=0)
    db.add(room)
    db.flush()
    db.add_all(
        [
            Task(name="Wipe counters", room_id=room.id, cadence_days=1, estimated_minutes=5),
            Task(name="Mop floor", room_id=room.id, cadence_days=7, estimated_minutes=20),
        ]
    )
    db.commit()
    result = call(client, owner_token, "list_tasks", {"name_contains": "mop", "room_id": room.id})
    assert result["isError"] is False
    assert [t["name"] for t in result["structuredContent"]["items"]] == ["Mop floor"]


def test_write_create_complete_and_undo(client, db, owner_token):
    created = call(
        client,
        owner_token,
        "create_task",
        {"name": "Clean microwave", "cadence_days": 7, "estimated_minutes": 10, "effort": "quick"},
    )
    assert created["isError"] is False
    task_id = created["structuredContent"]["id"]
    assert created["structuredContent"]["last_done_at"] is None

    done = call(client, owner_token, "complete_task", {"task_id": task_id})
    assert done["isError"] is False
    assert done["structuredContent"]["band"] == "fresh"
    completion_id = done["structuredContent"]["completion_id"]

    today = call(client, owner_token, "get_done_today")
    assert [c["id"] for c in today["structuredContent"]["completions"]] == [completion_id]

    undone = call(client, owner_token, "undo_completion", {"completion_id": completion_id})
    assert undone["isError"] is False
    assert undone["structuredContent"]["last_done_at"] is None


def test_write_flag_supply_low(client, db, owner_token):
    supply = Supply(name="Floor cleaner")
    db.add(supply)
    db.commit()
    result = call(client, owner_token, "update_supply", {"supply_id": supply.id, "status": "low"})
    assert result["isError"] is False
    assert result["structuredContent"]["status"] == "low"


def test_delete_room_keeps_its_tasks(client, db, owner_token):
    room = Room(name="Garage", sort_order=0)
    db.add(room)
    db.flush()
    task = Task(name="Sweep garage", room_id=room.id, cadence_days=30, estimated_minutes=15)
    db.add(task)
    db.commit()
    result = call(client, owner_token, "delete_room", {"room_id": room.id})
    assert result == {
        "content": [{"type": "text", "text": '{"ok":true}'}],
        "structuredContent": {"ok": True},
        "isError": False,
    }
    rooms = call(client, owner_token, "list_rooms")
    assert rooms["structuredContent"]["count"] == 0
    # The task survives (Postgres also nulls its room_id via the FK;
    # SQLite in tests doesn't enforce ON DELETE SET NULL).
    assert db.get(Task, task.id) is not None


def test_errors_are_plain_sentences(client, db, owner_token):
    missing = call(client, owner_token, "delete_task", {"task_id": 999})
    assert missing["isError"] is True
    assert missing["content"][0]["text"] == "Task not found."

    invalid = call(client, owner_token, "create_task", {"name": "x", "cadence_days": 0, "estimated_minutes": 5})
    assert invalid["isError"] is True
    assert invalid["content"][0]["text"].startswith("Some arguments weren't valid: cadence_days")


def test_kid_gets_chores_but_not_owner_tools(client, db, kid):
    db.add(Task(name="Feed the cat", cadence_days=1, estimated_minutes=5, assignee_id=kid.id))
    db.commit()
    token = _token_for(db, kid)
    overview = call(client, token, "get_overview")
    assert overview["isError"] is False
    assert [t["name"] for t in overview["structuredContent"]["chores"]["mine"]] == ["Feed the cat"]

    denied = call(client, token, "list_rooms")
    assert denied["isError"] is True
    assert "adult (owner) account" in denied["content"][0]["text"]


def test_owner_overview(client, db, owner_token):
    db.add(Supply(name="Sponges", status="out"))
    db.add(Task(name="Dust shelves", cadence_days=7, estimated_minutes=10))
    db.commit()
    result = call(client, owner_token, "get_overview")
    assert result["isError"] is False
    data = result["structuredContent"]
    assert data["you"]["role"] == "owner"
    assert [s["name"] for s in data["supplies_low_or_out"]] == ["Sponges"]
    assert [t["name"] for t in data["focus_tasks"]] == ["Dust shelves"]


def test_unknown_tool_is_a_jsonrpc_error(client, db, owner_token):
    response = client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "nope"}},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.json()["error"]["code"] == -32602
