"""OAuth 2.1 endpoints for the ChatGPT connector, plus the discovery
documents and the Settings "Connected apps" routes.

The flow ChatGPT runs (see CLAUDE.md "ChatGPT connector"):

1. POST /api/mcp without a token -> 401 pointing at the metadata below.
2. GET /.well-known/oauth-protected-resource[/api/mcp] and
   /.well-known/oauth-authorization-server.
3. POST /api/oauth/register (dynamic client registration).
4. GET /api/oauth/authorize -> the consent page (Tada session or PIN),
   POST -> 302 back to ChatGPT with a code (+ state, iss).
5. POST /api/oauth/token for the code, then for refreshes.

The browser and ChatGPT reach all of this through the frontend's proxy
(frontend/next.config.ts forwards /api/* and /.well-known/oauth-*), so
the Tada session cookie arrives here first-party.
"""

import hashlib
import json
import secrets
from datetime import datetime
from urllib.parse import parse_qsl, urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.routers.auth import require_owner
from app.services import oauth_pages
from app.services import oauth_service as oauth
from app.services.auth_service import SESSION_COOKIE_NAME, read_session_token, verify_pin

router = APIRouter(tags=["oauth"])

CSRF_COOKIE = "tada_oauth_csrf"
_CSRF_SALT = "tada-oauth-consent"
_CSRF_MAX_AGE = 30 * 60
#: The authorization-request parameters the consent form carries back.
_REQUEST_FIELDS = (
    "client_id",
    "redirect_uri",
    "response_type",
    "code_challenge",
    "code_challenge_method",
    "state",
    "scope",
    "resource",
)
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def require_mcp_enabled() -> None:
    """The kill switch (MCP_ENABLED=false) for the OAuth endpoints."""
    if not settings.mcp_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The ChatGPT connector is off")


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def _metadata_or_404(body: dict) -> JSONResponse:
    if not settings.mcp_enabled:
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    return JSONResponse(body, headers={"Cache-Control": "public, max-age=300"})


@router.get("/.well-known/oauth-protected-resource", include_in_schema=False)
@router.get("/.well-known/oauth-protected-resource/api/mcp", include_in_schema=False)
def protected_resource_metadata() -> JSONResponse:
    return _metadata_or_404(oauth.protected_resource_metadata())


@router.get("/.well-known/oauth-authorization-server", include_in_schema=False)
def authorization_server_metadata() -> JSONResponse:
    return _metadata_or_404(oauth.authorization_server_metadata())


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def _oauth_error(exc: oauth.OAuthError, extra_headers: dict | None = None) -> JSONResponse:
    headers = dict(_NO_STORE)
    if extra_headers:
        headers.update(extra_headers)
    return JSONResponse(
        {"error": exc.error, "error_description": exc.description},
        status_code=exc.status,
        headers=headers,
    )


@router.post(
    "/api/oauth/register",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_mcp_enabled)],
)
async def register(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    """RFC 7591 dynamic client registration — how ChatGPT introduces
    itself. Open by design (ChatGPT can't hold a registration secret);
    redirect URIs are pinned to ChatGPT's hosts or localhost."""
    try:
        payload = json.loads(await request.body() or b"{}")
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        return _oauth_error(oauth.OAuthError("invalid_client_metadata", "Body must be a JSON object."))
    try:
        reg = oauth.register_client(db, payload)
    except oauth.OAuthError as exc:
        return _oauth_error(exc)
    return JSONResponse(oauth.registration_response(reg), status_code=201, headers=_NO_STORE)


# ---------------------------------------------------------------------------
# Authorize (consent page)
# ---------------------------------------------------------------------------

def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=_CSRF_SALT)


def _params_digest(params: dict[str, str]) -> str:
    joined = "\n".join(f"{k}={params.get(k, '')}" for k in _REQUEST_FIELDS)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _csrf_token(nonce: str, params: dict[str, str]) -> str:
    """A signed token tying the form to this browser (the nonce cookie)
    and to this exact authorization request."""
    return _serializer().dumps({"n": nonce, "p": _params_digest(params)})


def _csrf_ok(token: str, nonce: str | None, params: dict[str, str]) -> bool:
    if not token or not nonce:
        return False
    try:
        data = _serializer().loads(token, max_age=_CSRF_MAX_AGE)
    except BadSignature:
        return False
    return (
        isinstance(data, dict)
        and secrets.compare_digest(str(data.get("n", "")), nonce)
        and data.get("p") == _params_digest(params)
    )


def _redirect(redirect_uri: str, **values: str | None) -> RedirectResponse:
    """302 back to the client with `iss` on every response (RFC 9207)."""
    query = {k: v for k, v in values.items() if v}
    query["iss"] = oauth.origin()
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(
        f"{redirect_uri}{sep}{urlencode(query)}", status_code=302, headers=_NO_STORE
    )


def _error_html(message: str, code: int = 400) -> HTMLResponse:
    return HTMLResponse(oauth_pages.error_page(message), status_code=code, headers=_NO_STORE)


def _session_user(request: Request, db: Session) -> User | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    user_id = read_session_token(token)
    return db.get(User, user_id) if user_id is not None else None


def _check_request(db: Session, params: dict[str, str]):
    """Validate an authorization request. Returns (client, redirect_uri,
    response): `response` is an error page or an error redirect to send
    instead, or None when the request is good."""
    client = oauth.get_client(db, params.get("client_id"))
    if client is None:
        return None, None, _error_html("Tada doesn’t recognise the app asking to connect.")
    registered = oauth.client_redirect_uris(client)
    redirect_uri = params.get("redirect_uri") or ""
    if not redirect_uri and len(registered) == 1:
        redirect_uri = registered[0]
    if redirect_uri not in registered:
        return client, None, _error_html("The return address for this connection isn’t registered.")

    state = params.get("state")
    if params.get("response_type") != "code":
        return client, redirect_uri, _redirect(
            redirect_uri, error="unsupported_response_type", state=state
        )
    if not params.get("code_challenge") or params.get("code_challenge_method") != "S256":
        return client, redirect_uri, _redirect(
            redirect_uri,
            error="invalid_request",
            error_description="PKCE with code_challenge_method=S256 is required.",
            state=state,
        )
    if not oauth.resource_matches(params.get("resource")):
        return client, redirect_uri, _redirect(
            redirect_uri, error="invalid_target", state=state
        )
    return client, redirect_uri, None


def _render_consent(
    params: dict[str, str],
    user: User | None,
    nonce: str,
    error: str | None = None,
    code: int = 200,
) -> HTMLResponse:
    hidden = {k: params.get(k, "") for k in _REQUEST_FIELDS}
    hidden["csrf"] = _csrf_token(nonce, params)
    response = HTMLResponse(
        oauth_pages.consent_page(
            hidden=hidden, user_name=user.name if user else None, error=error
        ),
        status_code=code,
        headers={**_NO_STORE, "X-Frame-Options": "DENY"},
    )
    response.set_cookie(
        CSRF_COOKIE,
        nonce,
        max_age=_CSRF_MAX_AGE,
        httponly=True,
        secure=oauth.origin().startswith("https://"),
        samesite="strict",
        path="/api/oauth",
    )
    return response


@router.get("/api/oauth/authorize", dependencies=[Depends(require_mcp_enabled)])
def authorize_page(request: Request, db: Session = Depends(get_db)) -> Response:
    params = {k: request.query_params.get(k, "") for k in _REQUEST_FIELDS}
    _, redirect_uri, problem = _check_request(db, params)
    if problem is not None:
        return problem
    params["redirect_uri"] = redirect_uri
    nonce = request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(24)
    return _render_consent(params, _session_user(request, db), nonce)


def _pin_user(db: Session, pin: str) -> User | None:
    """The same PIN check the app's login does (PINs are unique)."""
    users = db.scalars(select(User)).all()
    return next((u for u in users if verify_pin(pin, u.password_hash)), None)


@router.post("/api/oauth/authorize", dependencies=[Depends(require_mcp_enabled)])
async def authorize_submit(request: Request, db: Session = Depends(get_db)) -> Response:
    form = dict(parse_qsl((await request.body()).decode("utf-8"), keep_blank_values=True))
    params = {k: form.get(k, "") for k in _REQUEST_FIELDS}
    client, redirect_uri, problem = _check_request(db, params)
    if problem is not None:
        return problem
    params["redirect_uri"] = redirect_uri
    nonce = request.cookies.get(CSRF_COOKIE)
    if not _csrf_ok(form.get("csrf", ""), nonce, params):
        return _error_html("This sign-in page expired or was opened somewhere else.")

    state = params.get("state")
    if form.get("action") != "allow":
        return _redirect(redirect_uri, error="access_denied", state=state)

    pin = (form.get("pin") or "").strip()
    session_user = _session_user(request, db)
    if pin:
        if oauth.pin_attempts_blocked():
            return _render_consent(
                params, session_user, nonce, "Too many tries. Wait a few minutes, then try again.", 429
            )
        user = _pin_user(db, pin)
        if user is None:
            oauth.record_pin_failure()
            return _render_consent(params, session_user, nonce, "That PIN didn’t match. Try again.", 401)
    elif session_user is not None:
        user = session_user
    else:
        return _render_consent(params, None, nonce, "Enter your Tada PIN to continue.", 400)

    code = oauth.issue_code(
        db,
        client=client,
        user=user,
        redirect_uri=redirect_uri,
        code_challenge=params["code_challenge"],
        resource=params.get("resource") or None,
    )
    response = _redirect(redirect_uri, code=code, state=state)
    response.delete_cookie(CSRF_COOKIE, path="/api/oauth")
    return response


# ---------------------------------------------------------------------------
# Token + revoke
# ---------------------------------------------------------------------------

async def _read_form(request: Request) -> dict[str, str]:
    body = (await request.body()).decode("utf-8")
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            data = json.loads(body or "{}")
        except ValueError:
            return {}
        return {k: str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    return dict(parse_qsl(body, keep_blank_values=True))


@router.post("/api/oauth/token", dependencies=[Depends(require_mcp_enabled)])
async def token(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    form = await _read_form(request)
    authorization = request.headers.get("authorization")
    try:
        client = oauth.authenticate_client(db, form, authorization)
        grant = form.get("grant_type")
        if grant not in json.loads(client.grant_types):
            raise oauth.OAuthError("unauthorized_client", "This client may not use that grant.")
        if grant == "authorization_code":
            body = oauth.exchange_code(db, client, form)
        elif grant == "refresh_token":
            body = oauth.refresh(db, client, form)
        else:
            raise oauth.OAuthError("unsupported_grant_type", "Unsupported grant_type.")
    except oauth.OAuthError as exc:
        extra = (
            {"WWW-Authenticate": 'Basic realm="tada"'}
            if exc.status == 401 and authorization
            else None
        )
        return _oauth_error(exc, extra)
    return JSONResponse(body, headers=_NO_STORE)


@router.post("/api/oauth/revoke", dependencies=[Depends(require_mcp_enabled)])
async def revoke(request: Request, db: Session = Depends(get_db)) -> Response:
    form = await _read_form(request)
    try:
        client = oauth.authenticate_client(db, form, request.headers.get("authorization"))
    except oauth.OAuthError as exc:
        return _oauth_error(exc)
    oauth.revoke(db, client, form.get("token", ""))
    return Response(status_code=200, headers=_NO_STORE)


# ---------------------------------------------------------------------------
# Settings: connected apps
# ---------------------------------------------------------------------------

class ConnectionRead(BaseModel):
    client_name: str
    user_name: str
    last_used_at: datetime


class ConnectionsRead(BaseModel):
    enabled: bool
    connections: list[ConnectionRead]


@router.get("/api/oauth/connections", response_model=ConnectionsRead)
def list_connections(
    _: User = Depends(require_owner), db: Session = Depends(get_db)
) -> ConnectionsRead:
    """The Settings "Connected apps" card: who has connected ChatGPT."""
    return ConnectionsRead(
        enabled=settings.mcp_enabled,
        connections=[ConnectionRead(**c) for c in oauth.active_connections(db)],
    )


@router.delete("/api/oauth/connections", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_all(_: User = Depends(require_owner), db: Session = Depends(get_db)) -> None:
    """"Disconnect ChatGPT": revoke every token, so every connection has to
    sign in again on the consent page."""
    oauth.revoke_all(db)
