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
    samesite="none",
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


@router.post("/login", response_model=CurrentUserResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> User:
    # Phase 0 is single-owner: the PIN is checked against every owner
    # account (in practice, exactly one). Phase 2 adds kid logins alongside
    # this same flow.
    owners = db.scalars(select(User).where(User.role == "owner")).all()
    matched = next((u for u in owners if verify_pin(payload.pin, u.password_hash)), None)

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
