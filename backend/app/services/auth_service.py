import hmac

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings

SESSION_COOKIE_NAME = "tada_session"
_SESSION_SALT = "tada-session"


def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_pin(pin: str, password_hash: str) -> bool:
    return bcrypt.checkpw(pin.encode("utf-8"), password_hash.encode("utf-8"))


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=_SESSION_SALT)


def create_session_token(user_id: int) -> str:
    return _serializer().dumps({"user_id": user_id})


def read_session_token(token: str) -> int | None:
    """Returns the user_id encoded in a session token, or None if the token
    is missing, tampered with, or older than session_max_age_days."""
    max_age = settings.session_max_age_days * 24 * 60 * 60
    try:
        data = _serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("user_id")


def verify_device_token(presented: str) -> bool:
    """Whether `presented` matches the configured Hearth device token
    (docs/hearth-integration.md gap #1). Unlike the session cookie this
    authorizes the DEVICE, not a user — the acting household member is
    named per-request. Compared in constant time so a wrong token can't
    be recovered by timing. Returns False when the integration is
    disabled (no token set), so an unconfigured backend can never be
    unlocked by sending an empty bearer."""
    configured = settings.hearth_device_token
    if not configured:
        return False
    return hmac.compare_digest(presented, configured)
