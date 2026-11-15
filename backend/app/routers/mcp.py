"""The MCP server ChatGPT talks to: POST /api/mcp.

Streamable HTTP, stateless, JSON responses — a small hand-rolled JSON-RPC
handler (initialize, ping, tools/list, tools/call; notifications get 202).
Every request needs an OAuth access token from routers/oauth.py and acts
as the household member who approved the connection. Without one the
answer is 401 with the WWW-Authenticate header that starts ChatGPT's
OAuth discovery.

A tool call is dispatched as an in-process HTTP request to the real Tada
route (services/mcp_tools.py declares which), carrying a freshly minted
session cookie for that member. The route's own validation, owner-only
gate and side effects therefore apply unchanged.
"""

import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services import mcp_tools
from app.services import oauth_service as oauth
from app.services.auth_service import SESSION_COOKIE_NAME, create_session_token

log = logging.getLogger(__name__)

router = APIRouter(tags=["mcp"])

SUPPORTED_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
SERVER_INFO = {"name": "tada", "title": "Tada", "version": "1.0.0"}
INSTRUCTIONS = (
    "Tada is the household's cleaning coach. Tasks don't have due dates: each one decays "
    "from fresh to overdue based on how long since it was last done versus its cadence, and "
    "completing it resets the clock. Call get_overview first. Use list_* tools to find ids. "
    "Chores can need a parent check: \"checked\" means an adult physically inspected it, so "
    "only mark_checked when the parent says they looked. "
    "Be warm and never guilt-tripping: snoozing or skipping is always fine."
)
_INTERNAL_BASE = "http://tada.internal"


# ---------------------------------------------------------------------------
# HTTP entry points
# ---------------------------------------------------------------------------

def _unauthorized(error: str | None = None) -> JSONResponse:
    return JSONResponse(
        {"error": error or "unauthorized", "error_description": "Sign in to Tada through OAuth first."},
        status_code=401,
        headers={"WWW-Authenticate": oauth.www_authenticate(error)},
    )


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header[:7].lower() == "bearer ":
        return header[7:].strip()
    return None


@router.post("/api/mcp")
async def mcp_endpoint(request: Request, db: Session = Depends(get_db)) -> Response:
    if not settings.mcp_enabled:
        return JSONResponse({"detail": "The ChatGPT connector is off"}, status_code=503)

    token = _bearer(request)
    if token is None:
        return _unauthorized()
    user = oauth.user_for_access_token(db, token)
    if user is None:
        return _unauthorized("invalid_token")
    # Plain values only past this point: the shared session must not be
    # touched while tool calls run on their own sessions.
    user_id, user_role = user.id, user.role

    try:
        message = json.loads(await request.body())
    except ValueError:
        return JSONResponse(_error(None, -32700, "Parse error"), status_code=400)

    if isinstance(message, list):
        replies = [r for r in [await _handle(request, m, user_id, user_role) for m in message] if r]
        return JSONResponse(replies) if replies else Response(status_code=202)
    reply = await _handle(request, message, user_id, user_role)
    if reply is None:
        return Response(status_code=202)
    return JSONResponse(reply)


@router.get("/api/mcp")
@router.delete("/api/mcp")
def mcp_no_stream() -> Response:
    """Stateless server: no SSE stream to open and no session to end."""
    return Response(status_code=405, headers={"Allow": "POST"})


# ---------------------------------------------------------------------------
# JSON-RPC
# ---------------------------------------------------------------------------

def _result(msg_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


async def _handle(request: Request, message: Any, user_id: int, user_role: str) -> dict | None:
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, -32600, "Invalid Request")
    method = message.get("method")
    msg_id = message.get("id")
    if "id" not in message:
        return None  # a notification (e.g. notifications/initialized)
    params = message.get("params") or {}

    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]
        return _result(
            msg_id,
            {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
                "instructions": INSTRUCTIONS,
            },
        )
    if method == "ping":
        return _result(msg_id, {})
    if method == "tools/list":
        return _result(msg_id, {"tools": [t.definition() for t in mcp_tools.TOOLS]})
    if method == "tools/call":
        name = params.get("name")
        tool = mcp_tools.TOOLS_BY_NAME.get(name)
        if tool is None:
            return _error(msg_id, -32602, f"Unknown tool: {name}")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _error(msg_id, -32602, "arguments must be an object")
        return _result(msg_id, await run_tool(request.app, tool, arguments, user_id, user_role))
    return _error(msg_id, -32601, f"Method not found: {method}")


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

class ToolFailure(Exception):
    """A route answered with an error; `message` is a plain sentence."""


def _ok(data: Any) -> dict:
    if isinstance(data, dict):
        structured = data
    elif isinstance(data, list):
        structured = {"items": data, "count": len(data)}
    else:
        structured = {"result": data}
    return {
        "content": [{"type": "text", "text": json.dumps(structured, separators=(",", ":"), default=str)}],
        "structuredContent": structured,
        "isError": False,
    }


def _fail(message: str) -> dict:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _detail_sentence(status: int, body: Any) -> str:
    """FastAPI's detail as one sentence the model can act on."""
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, list):
        parts = []
        for entry in detail:
            if isinstance(entry, dict):
                where = ".".join(str(p) for p in entry.get("loc", [])[1:])
                parts.append(f"{where}: {entry.get('msg')}" if where else str(entry.get("msg")))
        detail = "; ".join(parts) or None
    if status == 403 and detail == "Owner only":
        return "That needs an adult (owner) account; this connection is signed in as a kid."
    if status == 422:
        return f"Some arguments weren't valid: {detail}."
    if detail:
        text = str(detail)
        return text if text.endswith((".", "!", "?")) else f"{text}."
    return f"Tada couldn't do that (HTTP {status})."


async def _call_route(
    client: httpx.AsyncClient, method: str, path: str, query: dict | None = None, body: dict | None = None
) -> Any:
    response = await client.request(method, path, params=query or None, json=body)
    if response.status_code == 204:
        return {"ok": True}
    try:
        data = response.json()
    except ValueError:
        data = None
    if response.status_code >= 400:
        raise ToolFailure(_detail_sentence(response.status_code, data))
    return data


def _build_request(tool: mcp_tools.Tool, arguments: dict) -> tuple[str, dict, dict | None]:
    """Split arguments into the route's path, query string and JSON body."""
    path = tool.path
    remaining = dict(arguments)
    for name in list(remaining):
        token = "{" + name + "}"
        if token in path:
            path = path.replace(token, str(int(remaining.pop(name))))
    if "{" in path:
        missing = path[path.index("{") + 1 : path.index("}")]
        raise ToolFailure(f"{missing} is required.")
    query = {k: remaining.pop(k) for k in tool.query if k in remaining and remaining[k] is not None}
    query = {k: str(v).lower() if isinstance(v, bool) else v for k, v in query.items()}
    body = remaining if tool.method in ("POST", "PUT", "PATCH") else None
    return path, query, body


def _shape(tool: mcp_tools.Tool, arguments: dict, data: Any) -> Any:
    if tool.shape == "filter_tasks" and isinstance(data, list):
        needle = (arguments.get("name_contains") or "").lower()
        band = arguments.get("band")
        return [
            t
            for t in data
            if (not needle or needle in t.get("name", "").lower())
            and (not band or t.get("band") == band)
        ]
    return data


async def _overview(client: httpx.AsyncClient, user_role: str) -> dict:
    """get_overview: several reads in one, matched to the member's role."""
    me = await _call_route(client, "GET", "/api/auth/me")
    if user_role != "owner":
        return {"you": me, "chores": await _call_route(client, "GET", "/api/chores")}
    focus = await _call_route(client, "GET", "/api/focus")
    done = await _call_route(client, "GET", "/api/done-today")
    rooms = await _call_route(client, "GET", "/api/rooms")
    supplies = await _call_route(client, "GET", "/api/supplies")
    app_settings = await _call_route(client, "GET", "/api/settings")
    chores = await _call_route(client, "GET", "/api/chores")
    checks = await _call_route(client, "GET", "/api/checks")
    return {
        "you": me,
        "focus_tasks": focus["tasks"],
        "total_active_tasks": focus["total_active_tasks"],
        "done_today": {
            "date": done["date"],
            "count": len(done["completions"]),
            "completions": done["completions"],
            "streak": done["streak"],
        },
        "rooms_needing_attention": [r for r in rooms if r.get("due_count")],
        "supplies_low_or_out": [s for s in supplies if s.get("status") in ("low", "out")],
        "my_assigned_chores": chores["mine"],
        "waiting_for_parent_check": checks["waiting"],
        "settings": app_settings,
    }


async def run_tool(app, tool: mcp_tools.Tool, arguments: dict, user_id: int, user_role: str) -> dict:
    """Run one tool as `user_id` against the app's own routes."""
    cookies = {SESSION_COOKIE_NAME: create_session_token(user_id)}
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url=_INTERNAL_BASE, cookies=cookies
        ) as client:
            if tool.name == "get_overview":
                return _ok(await _overview(client, user_role))
            path, query, body = _build_request(tool, arguments)
            data = await _call_route(client, tool.method, path, query, body)
            return _ok(_shape(tool, arguments, data))
    except ToolFailure as exc:
        return _fail(str(exc))
    except (TypeError, ValueError) as exc:
        return _fail(f"Some arguments weren't valid: {exc}.")
    except Exception:  # never leak a traceback to the model
        log.exception("MCP tool %s failed", tool.name)
        return _fail("Something went wrong inside Tada. Try again in a moment.")
