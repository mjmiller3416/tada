"""The ChatGPT connector's OAuth 2.1 server, end to end (routers/oauth.py,
routers/mcp.py, services/oauth_service.py).

Drives the real app through TestClient with the in-memory SQLite session
injected, the same pattern as test_hearth.py / test_orbit.py: discovery,
dynamic client registration, the consent page (with an existing Tada
session and with the PIN form), the token endpoint, the MCP endpoint, and
every failure the spec calls out — PKCE, redirect URI, replayed code,
expired token, refresh rotation, revocation and the kill switch.
"""

import base64
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings as app_settings
from app.database import get_db
from app.main import app
from app.models import OAuthToken, Room, Setting, User
from app.services import oauth_service
from app.services.auth_service import SESSION_COOKIE_NAME, create_session_token, hash_pin

ORIGIN = "https://tada.example.com"
REDIRECT = "https://chatgpt.com/connector_platform_oauth_redirect"
VERIFIER = "a-very-long-pkce-code-verifier-0123456789-abcdefghijklmnop"
PIN = "4321"


@pytest.fixture()
def client(db, monkeypatch):
    monkeypatch.setattr(app_settings, "frontend_url", ORIGIN + "/")
    monkeypatch.setattr(app_settings, "mcp_enabled", True)
    oauth_service.reset_pin_failures()
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app, base_url="https://testserver")
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def maryann(db):
    user = User(name="Maryann Miller", password_hash=hash_pin(PIN), role="owner")
    db.add(user)
    db.flush()
    db.add(Setting(user_id=user.id, key="timezone", value="UTC"))
    db.add(Room(name="Kitchen", sort_order=0))
    db.commit()
    return user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def register(client, method="none", redirect=REDIRECT) -> dict:
    response = client.post(
        "/api/oauth/register",
        json={
            "redirect_uris": [redirect],
            "client_name": "ChatGPT",
            "token_endpoint_auth_method": method,
            "grant_types": ["authorization_code", "refresh_token"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def auth_params(client_id, redirect=REDIRECT, **extra) -> dict:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect,
        "code_challenge": oauth_service.pkce_s256(VERIFIER),
        "code_challenge_method": "S256",
        "state": "state-123",
        "scope": "mcp",
        "resource": f"{ORIGIN}/api/mcp",
    }
    params.update(extra)
    return params


def hidden_fields(html: str) -> dict:
    return dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">', html))


def approve(client, client_id, pin=None, action="allow"):
    """GET the consent page, then submit it. Returns the POST response."""
    page = client.get("/api/oauth/authorize", params=auth_params(client_id))
    assert page.status_code == 200, page.text
    form = hidden_fields(page.text)
    form["action"] = action
    if pin is not None:
        form["pin"] = pin
    return client.post("/api/oauth/authorize", data=form, follow_redirects=False)


def code_from(response) -> str:
    assert response.status_code == 302, response.text
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["iss"] == [ORIGIN]
    assert query["state"] == ["state-123"]
    return query["code"][0]


def exchange(client, client_id, code, verifier=VERIFIER, redirect=REDIRECT, auth=None):
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": redirect,
        "client_id": client_id,
        "resource": f"{ORIGIN}/api/mcp",
    }
    headers = {}
    if auth:
        headers["Authorization"] = "Basic " + base64.b64encode(auth.encode()).decode()
        data.pop("client_id")
    return client.post("/api/oauth/token", data=data, headers=headers)


def connect(client, maryann) -> tuple[dict, dict]:
    """Register + approve with a Tada session + exchange: (client, tokens)."""
    reg = register(client)
    client.cookies.set(SESSION_COOKIE_NAME, create_session_token(maryann.id))
    code = code_from(approve(client, reg["client_id"]))
    client.cookies.delete(SESSION_COOKIE_NAME)
    tokens = exchange(client, reg["client_id"], code)
    assert tokens.status_code == 200, tokens.text
    return reg, tokens.json()


def mcp(client, token, method, params=None, msg_id=1):
    return client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}},
        headers={"Authorization": f"Bearer {token}"},
    )


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def test_mcp_without_token_is_401_with_resource_metadata(client):
    response = client.post("/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == (
        f'Bearer resource_metadata="{ORIGIN}/.well-known/oauth-protected-resource", scope="mcp"'
    )


def test_protected_resource_metadata_at_both_paths(client):
    for path in (
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-protected-resource/api/mcp",
    ):
        body = client.get(path).json()
        assert body["resource"] == f"{ORIGIN}/api/mcp"
        assert body["authorization_servers"] == [ORIGIN]
        assert body["scopes_supported"] == ["mcp"]
        assert body["bearer_methods_supported"] == ["header"]


def test_authorization_server_metadata(client):
    body = client.get("/.well-known/oauth-authorization-server").json()
    assert body["issuer"] == ORIGIN
    assert body["authorization_endpoint"] == f"{ORIGIN}/api/oauth/authorize"
    assert body["token_endpoint"] == f"{ORIGIN}/api/oauth/token"
    assert body["registration_endpoint"] == f"{ORIGIN}/api/oauth/register"
    assert body["revocation_endpoint"] == f"{ORIGIN}/api/oauth/revoke"
    assert body["code_challenge_methods_supported"] == ["S256"]
    assert body["authorization_response_iss_parameter_supported"] is True
    assert "client_id_metadata_document_supported" not in body
    assert client.get("/.well-known/openid-configuration").status_code == 404


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_registration_issues_a_secret_unless_public(client):
    confidential = register(client, method="client_secret_basic")
    assert confidential["client_secret"]
    assert confidential["token_endpoint_auth_method"] == "client_secret_basic"
    public = register(client, method="none")
    assert "client_secret" not in public
    assert public["redirect_uris"] == [REDIRECT]


@pytest.mark.parametrize(
    "uri",
    ["https://evil.example.com/cb", "http://chatgpt.com/cb", "https://chatgpt.com.evil.io/cb"],
)
def test_registration_rejects_foreign_redirects(client, uri):
    response = client.post("/api/oauth/register", json={"redirect_uris": [uri]})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_redirect_uri"


def test_registration_allows_localhost_for_tests(client):
    assert register(client, redirect="http://localhost:6274/callback")["client_id"]


# ---------------------------------------------------------------------------
# The full round trip
# ---------------------------------------------------------------------------

def test_round_trip_with_existing_session(client, maryann):
    reg = register(client)
    client.cookies.set(SESSION_COOKIE_NAME, create_session_token(maryann.id))
    page = client.get("/api/oauth/authorize", params=auth_params(reg["client_id"]))
    assert "Signed in as Maryann Miller" in page.text
    assert "ChatGPT wants to use Tada as you, Maryann." in page.text
    assert "It will be able to see and change everything you can." in page.text

    code = code_from(approve(client, reg["client_id"]))
    client.cookies.delete(SESSION_COOKIE_NAME)
    tokens = exchange(client, reg["client_id"], code)
    assert tokens.status_code == 200
    assert tokens.headers["cache-control"] == "no-store"
    body = tokens.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 3600
    assert body["scope"] == "mcp"

    init = mcp(client, body["access_token"], "initialize", {"protocolVersion": "2025-06-18"})
    assert init.json()["result"]["protocolVersion"] == "2025-06-18"
    assert init.json()["result"]["capabilities"]["tools"] == {"listChanged": False}

    note = client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert note.status_code == 202

    tools = mcp(client, body["access_token"], "tools/list").json()["result"]["tools"]
    assert any(t["name"] == "list_rooms" for t in tools)

    call = mcp(client, body["access_token"], "tools/call", {"name": "list_rooms", "arguments": {}})
    result = call.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["items"][0]["name"] == "Kitchen"
    assert result["content"][0]["type"] == "text"


def test_round_trip_with_pin_form_and_basic_client_auth(client, maryann):
    reg = register(client, method="client_secret_basic")
    page = client.get("/api/oauth/authorize", params=auth_params(reg["client_id"]))
    assert 'name="pin"' in page.text and "Signed in as" not in page.text

    no_pin = approve(client, reg["client_id"])
    assert no_pin.status_code == 400 and "Enter your Tada PIN" in no_pin.text
    wrong = approve(client, reg["client_id"], pin="0000")
    assert wrong.status_code == 401 and "didn’t match" in wrong.text

    code = code_from(approve(client, reg["client_id"], pin=PIN))
    bad_secret = exchange(client, reg["client_id"], code, auth=f"{reg['client_id']}:nope")
    assert bad_secret.status_code == 401
    assert bad_secret.json()["error"] == "invalid_client"

    code = code_from(approve(client, reg["client_id"], pin=PIN))
    tokens = exchange(client, reg["client_id"], code, auth=f"{reg['client_id']}:{reg['client_secret']}")
    assert tokens.status_code == 200
    me = mcp(client, tokens.json()["access_token"], "tools/call", {"name": "who_am_i", "arguments": {}})
    assert me.json()["result"]["structuredContent"]["name"] == "Maryann Miller"


def test_cancel_redirects_access_denied_with_iss(client, maryann):
    reg = register(client)
    response = approve(client, reg["client_id"], action="cancel")
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["error"] == ["access_denied"]
    assert query["iss"] == [ORIGIN]
    assert query["state"] == ["state-123"]


def test_consent_post_needs_the_csrf_token(client, maryann):
    reg = register(client)
    client.cookies.set(SESSION_COOKIE_NAME, create_session_token(maryann.id))
    page = client.get("/api/oauth/authorize", params=auth_params(reg["client_id"]))
    form = hidden_fields(page.text)
    form["action"] = "allow"
    form["csrf"] = "forged"
    response = client.post("/api/oauth/authorize", data=form, follow_redirects=False)
    assert response.status_code == 400
    assert "location" not in response.headers

    # A token for one request can't approve a different one.
    form = hidden_fields(page.text)
    form["action"] = "allow"
    form["state"] = "other-state"
    response = client.post("/api/oauth/authorize", data=form, follow_redirects=False)
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Failures
# ---------------------------------------------------------------------------

def test_unknown_client_or_redirect_shows_error_page_never_redirects(client, maryann):
    reg = register(client)
    unknown = client.get("/api/oauth/authorize", params=auth_params("nope"), follow_redirects=False)
    assert unknown.status_code == 400 and "location" not in unknown.headers
    wrong = client.get(
        "/api/oauth/authorize",
        params=auth_params(reg["client_id"], redirect="https://chatgpt.com/other"),
        follow_redirects=False,
    )
    assert wrong.status_code == 400 and "location" not in wrong.headers


def test_missing_pkce_and_wrong_resource_redirect_with_errors(client, maryann):
    reg = register(client)
    no_pkce = client.get(
        "/api/oauth/authorize",
        params=auth_params(reg["client_id"], code_challenge_method="plain"),
        follow_redirects=False,
    )
    assert parse_qs(urlsplit(no_pkce.headers["location"]).query)["error"] == ["invalid_request"]
    wrong_resource = client.get(
        "/api/oauth/authorize",
        params=auth_params(reg["client_id"], resource="https://elsewhere.example/api/mcp"),
        follow_redirects=False,
    )
    query = parse_qs(urlsplit(wrong_resource.headers["location"]).query)
    assert query["error"] == ["invalid_target"] and query["iss"] == [ORIGIN]
    # A trailing slash on the resource is tolerated.
    ok = client.get(
        "/api/oauth/authorize",
        params=auth_params(reg["client_id"], resource=f"{ORIGIN}/api/mcp/"),
    )
    assert ok.status_code == 200


def test_pkce_failure(client, maryann):
    reg = register(client)
    code = code_from(approve(client, reg["client_id"], pin=PIN))
    response = exchange(client, reg["client_id"], code, verifier="wrong-verifier-" + "x" * 40)
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_grant"


def test_wrong_redirect_uri_at_token(client, maryann):
    reg = register(client)
    code = code_from(approve(client, reg["client_id"], pin=PIN))
    response = exchange(client, reg["client_id"], code, redirect="https://chatgpt.com/other")
    assert response.json()["error"] == "invalid_grant"


def test_reused_code_is_rejected_and_revokes_its_tokens(client, maryann):
    reg = register(client)
    code = code_from(approve(client, reg["client_id"], pin=PIN))
    first = exchange(client, reg["client_id"], code).json()
    assert mcp(client, first["access_token"], "ping").status_code == 200

    again = exchange(client, reg["client_id"], code)
    assert again.status_code == 400
    assert again.json()["error"] == "invalid_grant"
    assert mcp(client, first["access_token"], "ping").status_code == 401


def test_refresh_rotates_and_old_refresh_is_rejected(client, maryann):
    reg, tokens = connect(client, maryann)
    refreshed = client.post(
        "/api/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": reg["client_id"],
        },
    )
    assert refreshed.status_code == 200
    new = refreshed.json()
    assert new["refresh_token"] != tokens["refresh_token"]
    assert mcp(client, new["access_token"], "ping").status_code == 200

    reuse = client.post(
        "/api/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": reg["client_id"],
        },
    )
    assert reuse.status_code == 400
    assert reuse.json()["error"] == "invalid_grant"


def test_expired_access_token_is_401_with_header(client, maryann, db):
    _, tokens = connect(client, maryann)
    row = db.scalar(
        select(OAuthToken).where(
            OAuthToken.token_hash == oauth_service.hash_secret(tokens["access_token"])
        )
    )
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    response = mcp(client, tokens["access_token"], "ping")
    assert response.status_code == 401
    assert 'resource_metadata="https://tada.example.com/.well-known/oauth-protected-resource"' in (
        response.headers["www-authenticate"]
    )
    assert 'error="invalid_token"' in response.headers["www-authenticate"]


def test_revoke_refresh_token_ends_the_connection(client, maryann):
    reg, tokens = connect(client, maryann)
    response = client.post(
        "/api/oauth/revoke",
        data={"token": tokens["refresh_token"], "client_id": reg["client_id"]},
    )
    assert response.status_code == 200
    assert mcp(client, tokens["access_token"], "ping").status_code == 401
    refresh = client.post(
        "/api/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": reg["client_id"],
        },
    )
    assert refresh.json()["error"] == "invalid_grant"


def test_pin_attempts_are_throttled(client, maryann):
    reg = register(client)
    for _ in range(10):
        approve(client, reg["client_id"], pin="0000")
    blocked = approve(client, reg["client_id"], pin=PIN)
    assert blocked.status_code == 429


# ---------------------------------------------------------------------------
# Kill switch + Settings
# ---------------------------------------------------------------------------

def test_kill_switch_turns_everything_off(client, maryann, monkeypatch):
    _, tokens = connect(client, maryann)
    monkeypatch.setattr(app_settings, "mcp_enabled", False)
    assert mcp(client, tokens["access_token"], "ping").status_code == 503
    assert client.get("/.well-known/oauth-authorization-server").status_code == 404
    assert client.post("/api/oauth/register", json={"redirect_uris": [REDIRECT]}).status_code == 503


def test_settings_lists_and_disconnects_connections(client, maryann):
    _, tokens = connect(client, maryann)
    client.cookies.set(SESSION_COOKIE_NAME, create_session_token(maryann.id))
    listed = client.get("/api/oauth/connections").json()
    assert listed["enabled"] is True
    assert [c["user_name"] for c in listed["connections"]] == ["Maryann Miller"]

    assert client.delete("/api/oauth/connections").status_code == 204
    assert client.get("/api/oauth/connections").json()["connections"] == []
    client.cookies.delete(SESSION_COOKIE_NAME)
    assert mcp(client, tokens["access_token"], "ping").status_code == 401
