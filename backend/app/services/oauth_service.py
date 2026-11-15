"""The OAuth 2.1 authorization server behind the ChatGPT connector.

ChatGPT can only reach a custom MCP server through OAuth (no static
tokens), so Tada runs a small authorization server of its own:

- dynamic client registration (RFC 7591),
- the authorization-code grant with mandatory PKCE S256,
- refresh tokens that rotate on every use (RFC 6749 §10.4 / OAuth 2.1),
- revocation (RFC 7009).

Everything secret — client secrets, codes, access and refresh tokens — is
an opaque random string handed out once and stored only as its SHA-256
hash. The public origin (issuer, resource) comes from FRONTEND_URL, never
from a request's Host header: ChatGPT and the browser reach this backend
only through the frontend's /api proxy.

The HTTP shapes live in routers/oauth.py; this module is the logic and is
what the tests exercise underneath the routes.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote_plus, urlsplit

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.models.oauth import OAuthClient, OAuthCode, OAuthToken
from app.models.user import User

SCOPE = "mcp"
ACCESS_TOKEN_SECONDS = 3600
REFRESH_TOKEN_DAYS = 90
CODE_MINUTES = 10

AUTH_METHODS = ("none", "client_secret_post", "client_secret_basic")
CHATGPT_HOSTS = ("chatgpt.com", "chat.openai.com")
LOCAL_HOSTS = ("localhost", "127.0.0.1")


class OAuthError(Exception):
    """An RFC 6749-style error: `error` is the machine code, `description`
    a plain sentence, `status` the HTTP status the token endpoint uses."""

    def __init__(self, error: str, description: str, status: int = 400):
        super().__init__(description)
        self.error = error
        self.description = description
        self.status = status


# ---------------------------------------------------------------------------
# Origin and small helpers
# ---------------------------------------------------------------------------

def origin() -> str:
    """The public origin ChatGPT sees — FRONTEND_URL without a trailing
    slash. It is the issuer, and `<origin>/api/mcp` is the resource."""
    return settings.frontend_url.rstrip("/")


def resource_url() -> str:
    return f"{origin()}/api/mcp"


def resource_matches(resource: str | None) -> bool:
    """A `resource` parameter, when sent, must name this MCP server.
    A trailing slash is tolerated."""
    if resource is None or resource == "":
        return True
    return resource.rstrip("/") == resource_url()


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_secret() -> str:
    """An opaque, URL-safe random string with 32 bytes of entropy."""
    return secrets.token_urlsafe(32)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; treat those as UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def pkce_s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# ---------------------------------------------------------------------------
# Discovery documents
# ---------------------------------------------------------------------------

def protected_resource_metadata() -> dict:
    """RFC 9728 metadata for the MCP endpoint."""
    return {
        "resource": resource_url(),
        "authorization_servers": [origin()],
        "scopes_supported": [SCOPE],
        "bearer_methods_supported": ["header"],
        "resource_name": "Tada",
    }


def authorization_server_metadata() -> dict:
    """RFC 8414 metadata. Deliberately no OpenID fields (ChatGPT would ask
    for every advertised OIDC scope) and no CIMD — ChatGPT uses DCR."""
    base = origin()
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/api/oauth/authorize",
        "token_endpoint": f"{base}/api/oauth/token",
        "registration_endpoint": f"{base}/api/oauth/register",
        "revocation_endpoint": f"{base}/api/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": list(AUTH_METHODS),
        "revocation_endpoint_auth_methods_supported": list(AUTH_METHODS),
        "scopes_supported": [SCOPE],
        "authorization_response_iss_parameter_supported": True,
    }


def www_authenticate(error: str | None = None) -> str:
    """The header every unauthenticated /api/mcp answer carries, pointing
    ChatGPT at the protected-resource metadata."""
    value = (
        f'Bearer resource_metadata="{origin()}/.well-known/oauth-protected-resource", '
        f'scope="{SCOPE}"'
    )
    if error:
        value += f', error="{error}"'
    return value


# ---------------------------------------------------------------------------
# Dynamic client registration
# ---------------------------------------------------------------------------

def redirect_uri_allowed(uri: str) -> bool:
    """https on ChatGPT's hosts, or plain http on localhost for local
    tests. Nothing else may receive a code."""
    try:
        parts = urlsplit(uri)
    except ValueError:
        return False
    if parts.fragment:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme == "https" and host in CHATGPT_HOSTS:
        return True
    return parts.scheme == "http" and host in LOCAL_HOSTS


@dataclass
class Registration:
    client: OAuthClient
    secret: str | None


def register_client(db: Session, payload: dict) -> Registration:
    """Validate a DCR request and store the client. Raises OAuthError
    (invalid_redirect_uri / invalid_client_metadata) on bad input."""
    redirect_uris = payload.get("redirect_uris")
    if not isinstance(redirect_uris, list) or not redirect_uris:
        raise OAuthError("invalid_redirect_uri", "redirect_uris must be a non-empty list.")
    for uri in redirect_uris:
        if not isinstance(uri, str) or not redirect_uri_allowed(uri):
            raise OAuthError(
                "invalid_redirect_uri",
                f"Redirect URI not allowed: {uri!r}. Only ChatGPT (https) or localhost may register.",
            )

    method = payload.get("token_endpoint_auth_method") or "client_secret_basic"
    if method not in AUTH_METHODS:
        raise OAuthError(
            "invalid_client_metadata",
            f"token_endpoint_auth_method must be one of {', '.join(AUTH_METHODS)}.",
        )

    grant_types = payload.get("grant_types") or ["authorization_code", "refresh_token"]
    if not isinstance(grant_types, list) or any(
        g not in ("authorization_code", "refresh_token") for g in grant_types
    ):
        raise OAuthError(
            "invalid_client_metadata",
            "grant_types may only contain authorization_code and refresh_token.",
        )
    response_types = payload.get("response_types") or ["code"]
    if response_types != ["code"]:
        raise OAuthError("invalid_client_metadata", 'response_types must be ["code"].')

    name = payload.get("client_name")
    name = str(name)[:200] if name else None

    secret = None if method == "none" else new_secret()
    client = OAuthClient(
        client_id=secrets.token_urlsafe(24),
        secret_hash=hash_secret(secret) if secret else None,
        client_name=name,
        redirect_uris=json.dumps(redirect_uris),
        token_endpoint_auth_method=method,
        grant_types=json.dumps(grant_types),
        created_at=_now(),
    )
    db.add(client)
    db.commit()
    return Registration(client=client, secret=secret)


def registration_response(reg: Registration) -> dict:
    client = reg.client
    body = {
        "client_id": client.client_id,
        "client_id_issued_at": int(_aware(client.created_at).timestamp()),
        "client_name": client.client_name,
        "redirect_uris": json.loads(client.redirect_uris),
        "token_endpoint_auth_method": client.token_endpoint_auth_method,
        "grant_types": json.loads(client.grant_types),
        "response_types": ["code"],
        "scope": SCOPE,
    }
    if reg.secret:
        body["client_secret"] = reg.secret
        body["client_secret_expires_at"] = 0  # never
    return body


def get_client(db: Session, client_id: str | None) -> OAuthClient | None:
    if not client_id:
        return None
    return db.get(OAuthClient, client_id)


def client_redirect_uris(client: OAuthClient) -> list[str]:
    return json.loads(client.redirect_uris)


def authenticate_client(
    db: Session,
    form: dict,
    authorization: str | None,
) -> OAuthClient:
    """Authenticate the caller of the token/revoke endpoints per the
    client's registered method. Secrets compare in constant time."""
    client_id = form.get("client_id")
    secret = form.get("client_secret")
    if authorization and authorization.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(authorization[6:].strip()).decode("utf-8")
            basic_id, _, basic_secret = decoded.partition(":")
        except (ValueError, UnicodeDecodeError):
            raise OAuthError("invalid_client", "Malformed Basic credentials.", 401)
        client_id, secret = unquote_plus(basic_id), unquote_plus(basic_secret)

    client = get_client(db, client_id)
    if client is None:
        raise OAuthError("invalid_client", "Unknown client.", 401)
    if client.token_endpoint_auth_method == "none":
        return client
    if not secret or client.secret_hash is None:
        raise OAuthError("invalid_client", "Client authentication failed.", 401)
    if not hmac.compare_digest(hash_secret(secret), client.secret_hash):
        raise OAuthError("invalid_client", "Client authentication failed.", 401)
    return client


# ---------------------------------------------------------------------------
# Authorization codes
# ---------------------------------------------------------------------------

def issue_code(
    db: Session,
    *,
    client: OAuthClient,
    user: User,
    redirect_uri: str,
    code_challenge: str,
    resource: str | None,
) -> str:
    """A single-use code for the consent the user just gave."""
    code = new_secret()
    db.add(
        OAuthCode(
            code_hash=hash_secret(code),
            client_id=client.client_id,
            user_id=user.id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            resource=resource or None,
            scope=SCOPE,
            expires_at=_now() + timedelta(minutes=CODE_MINUTES),
            created_at=_now(),
        )
    )
    db.commit()
    return code


def _new_token(
    db: Session,
    *,
    kind: str,
    client_id: str,
    user_id: int,
    code_id: int | None,
    resource: str | None,
    lifetime: timedelta,
) -> str:
    value = new_secret()
    db.add(
        OAuthToken(
            token_hash=hash_secret(value),
            kind=kind,
            client_id=client_id,
            user_id=user_id,
            code_id=code_id,
            scope=SCOPE,
            resource=resource,
            expires_at=_now() + lifetime,
            created_at=_now(),
        )
    )
    return value


def _token_pair(
    db: Session, *, client_id: str, user_id: int, code_id: int | None, resource: str | None
) -> dict:
    access = _new_token(
        db,
        kind="access",
        client_id=client_id,
        user_id=user_id,
        code_id=code_id,
        resource=resource,
        lifetime=timedelta(seconds=ACCESS_TOKEN_SECONDS),
    )
    refresh = _new_token(
        db,
        kind="refresh",
        client_id=client_id,
        user_id=user_id,
        code_id=code_id,
        resource=resource,
        lifetime=timedelta(days=REFRESH_TOKEN_DAYS),
    )
    db.commit()
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": ACCESS_TOKEN_SECONDS,
        "refresh_token": refresh,
        "scope": SCOPE,
    }


def _revoke_family(db: Session, code_id: int) -> None:
    db.execute(
        update(OAuthToken)
        .where(OAuthToken.code_id == code_id, OAuthToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


def exchange_code(db: Session, client: OAuthClient, form: dict) -> dict:
    """grant_type=authorization_code: verify the code (unused, unexpired,
    same client and redirect URI, PKCE) and issue the first token pair.
    A replayed code revokes every token it ever produced."""
    code_value = form.get("code") or ""
    verifier = form.get("code_verifier") or ""
    redirect_uri = form.get("redirect_uri") or ""

    code = db.scalar(select(OAuthCode).where(OAuthCode.code_hash == hash_secret(code_value)))
    if code is None or code.client_id != client.client_id:
        raise OAuthError("invalid_grant", "Unknown or mismatched authorization code.")
    if code.used_at is not None:
        _revoke_family(db, code.id)
        db.commit()
        raise OAuthError("invalid_grant", "This authorization code was already used.")
    # Mark used before any further check, so a failed attempt can't be
    # retried with a guessed verifier.
    code.used_at = _now()
    db.commit()

    if _aware(code.expires_at) <= _now():
        raise OAuthError("invalid_grant", "The authorization code has expired.")
    if redirect_uri != code.redirect_uri:
        raise OAuthError("invalid_grant", "redirect_uri does not match the authorization request.")
    if not verifier or not hmac.compare_digest(pkce_s256(verifier), code.code_challenge):
        raise OAuthError("invalid_grant", "PKCE verification failed.")
    resource = form.get("resource")
    if not resource_matches(resource):
        raise OAuthError("invalid_target", "Unknown resource.")

    return _token_pair(
        db,
        client_id=client.client_id,
        user_id=code.user_id,
        code_id=code.id,
        resource=code.resource,
    )


def refresh(db: Session, client: OAuthClient, form: dict) -> dict:
    """grant_type=refresh_token: rotate. The presented refresh token is
    revoked and a new pair issued; the new refresh token lives 90 days
    from now, i.e. from its last use."""
    value = form.get("refresh_token") or ""
    token = db.scalar(
        select(OAuthToken).where(
            OAuthToken.token_hash == hash_secret(value), OAuthToken.kind == "refresh"
        )
    )
    if token is None or token.client_id != client.client_id:
        raise OAuthError("invalid_grant", "Unknown refresh token.")
    if token.revoked_at is not None:
        raise OAuthError("invalid_grant", "This refresh token is no longer valid.")
    if _aware(token.expires_at) <= _now():
        raise OAuthError("invalid_grant", "The refresh token has expired.")
    if not resource_matches(form.get("resource")):
        raise OAuthError("invalid_target", "Unknown resource.")
    if db.get(User, token.user_id) is None:
        raise OAuthError("invalid_grant", "That household member no longer exists.")

    token.revoked_at = _now()
    return _token_pair(
        db,
        client_id=client.client_id,
        user_id=token.user_id,
        code_id=token.code_id,
        resource=token.resource,
    )


def revoke(db: Session, client: OAuthClient, value: str) -> None:
    """RFC 7009: revoke the token if it's this client's; unknown tokens
    are not an error. Revoking a refresh token also revokes its access
    tokens (the same code family)."""
    token = db.scalar(select(OAuthToken).where(OAuthToken.token_hash == hash_secret(value)))
    if token is None or token.client_id != client.client_id:
        return
    if token.revoked_at is None:
        token.revoked_at = _now()
    if token.kind == "refresh" and token.code_id is not None:
        _revoke_family(db, token.code_id)
    db.commit()


# ---------------------------------------------------------------------------
# Resource-server side
# ---------------------------------------------------------------------------

def user_for_access_token(db: Session, value: str) -> User | None:
    """The household member an access token acts as, or None if the
    token is unknown, revoked or expired."""
    if not value:
        return None
    token = db.scalar(
        select(OAuthToken).where(
            OAuthToken.token_hash == hash_secret(value), OAuthToken.kind == "access"
        )
    )
    if token is None or token.revoked_at is not None:
        return None
    if _aware(token.expires_at) <= _now():
        return None
    return db.get(User, token.user_id)


def active_connections(db: Session) -> list[dict]:
    """Every live connection (an unrevoked, unexpired refresh token), for
    the Settings "Connected apps" card."""
    rows = db.execute(
        select(OAuthToken, OAuthClient, User)
        .join(OAuthClient, OAuthToken.client_id == OAuthClient.client_id)
        .join(User, OAuthToken.user_id == User.id)
        .where(OAuthToken.kind == "refresh", OAuthToken.revoked_at.is_(None))
        .order_by(OAuthToken.created_at.desc())
    ).all()
    now = _now()
    return [
        {
            "client_name": client.client_name or "ChatGPT",
            "user_name": user.name,
            "last_used_at": _aware(token.created_at),
        }
        for token, client, user in rows
        if _aware(token.expires_at) > now
    ]


def revoke_all(db: Session) -> int:
    """The kill switch's second half: revoke every outstanding token so
    every connection must sign in again. Returns how many were live."""
    result = db.execute(
        update(OAuthToken).where(OAuthToken.revoked_at.is_(None)).values(revoked_at=_now())
    )
    db.commit()
    return result.rowcount or 0


# ---------------------------------------------------------------------------
# Consent-page PIN throttle
# ---------------------------------------------------------------------------

_PIN_WINDOW_SECONDS = 15 * 60
_PIN_MAX_FAILURES = 10
_pin_failures: list[float] = []


def pin_attempts_blocked() -> bool:
    """The consent page takes a PIN from the public internet; after ten
    wrong PINs in fifteen minutes it stops checking for a while. Global
    on purpose: one household, one door."""
    cutoff = time.monotonic() - _PIN_WINDOW_SECONDS
    _pin_failures[:] = [t for t in _pin_failures if t > cutoff]
    return len(_pin_failures) >= _PIN_MAX_FAILURES


def record_pin_failure() -> None:
    _pin_failures.append(time.monotonic())


def reset_pin_failures() -> None:
    _pin_failures.clear()
