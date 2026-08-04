from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.auth import CurrentUserResponse, LoginRequest
from app.services.auth_service import (
    SESSION_COOKIE_NAME,
    create_session_token,
    read_session_token,
    verify_pin,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_COOKIE_KWARGS = dict(
    httponly=True,
    secure=True,
    # "lax" not "none": the frontend proxies /api/* through its own origin
    # (see frontend/next.config.ts), so this cookie is first-party. It used
    # to be a genuine cross-site cookie between two Railway origins, which
    # iOS Safari (esp. standalone/home-screen PWA mode) silently refuses to
    # persist via ITP — login would "succeed" but the session never stuck.
    samesite="lax",
    max_age=settings.session_max_age_days * 24 * 60 * 60,
    path="/",
)


def get_current_user(
    tada_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    if tada_session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    user_id = read_session_token(tada_session)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired or invalid")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")

    return user


def require_owner(current_user: User = Depends(get_current_user)) -> User:
    """Gate for owner-only surfaces (planning, settings, household,
    supplies). Kids get the deliberately small chores surface (SPEC §6:
    'basic functionality only')."""
    if current_user.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Owner only")
    return current_user


@router.post("/login", response_model=CurrentUserResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> User:
    # One shared login flow for everyone: the PIN is checked against every
    # user. PINs are kept unique across users (enforced when members are
    # created/updated), so a match identifies exactly one person.
    users = db.scalars(select(User)).all()
    matched = next((u for u in users if verify_pin(payload.pin, u.password_hash)), None)

    if matched is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect PIN")

    token = create_session_token(matched.id)
    response.set_cookie(SESSION_COOKIE_NAME, token, **_COOKIE_KWARGS)
    return matched


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


@router.get("/me", response_model=CurrentUserResponse)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
