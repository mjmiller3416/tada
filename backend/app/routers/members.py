from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.task import Task
from app.models.user import User
from app.routers.auth import require_owner
from app.schemas.members import MemberCreate, MemberRead, MemberUpdate
from app.services.auth_service import hash_pin, verify_pin

router = APIRouter(prefix="/api/members", tags=["members"])


def _assigned_counts(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(Task.assignee_id, func.count(Task.id))
        .where(Task.assignee_id.is_not(None), Task.is_active.is_(True))
        .group_by(Task.assignee_id)
    ).all()
    return {assignee_id: count for assignee_id, count in rows}


def _to_read(user: User, assigned_counts: dict[int, int]) -> MemberRead:
    return MemberRead(
        id=user.id,
        name=user.name,
        role=user.role,
        assigned_count=assigned_counts.get(user.id, 0),
    )


def _check_pin_free(db: Session, pin: str, exclude_user_id: int | None = None) -> None:
    """Login is PIN-only, so a PIN must identify exactly one person. A
    collision would silently log someone in as somebody else."""
    users = db.scalars(select(User)).all()
    for user in users:
        if user.id != exclude_user_id and verify_pin(pin, user.password_hash):
            raise HTTPException(
                status.HTTP_409_CONFLICT, "That PIN is taken — pick a different one"
            )


def _get_member(db: Session, member_id: int) -> User:
    """Any household account — kids and owners alike. Since Phase 4.6
    this surface manages adults too (the seed script is only needed for
    the very first owner)."""
    user = db.get(User, member_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    return user


@router.get("", response_model=list[MemberRead])
def list_members(
    _: User = Depends(require_owner), db: Session = Depends(get_db)
) -> list[MemberRead]:
    """Everyone in the household (owner included, so the assign dropdown
    can offer her too), kids after the owner."""
    users = db.scalars(select(User).order_by(User.role.desc(), User.id)).all()
    counts = _assigned_counts(db)
    return [_to_read(user, counts) for user in users]


@router.post("", response_model=MemberRead, status_code=status.HTTP_201_CREATED)
def create_member(
    payload: MemberCreate,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> MemberRead:
    """A new kid login, or — Phase 4.6 — a second adult. An adult
    (role "owner") sees and can change everything she can: no data is
    scoped per user and `require_owner` only checks the role, so shared
    access needs nothing beyond the account itself."""
    _check_pin_free(db, payload.pin)
    member = User(
        name=payload.name,
        email=None,
        role=payload.role,
        password_hash=hash_pin(payload.pin),
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return _to_read(member, {})


@router.patch("/{member_id}", response_model=MemberRead)
def update_member(
    member_id: int,
    payload: MemberUpdate,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> MemberRead:
    member = _get_member(db, member_id)
    if payload.name is not None:
        member.name = payload.name
    if payload.pin is not None:
        _check_pin_free(db, payload.pin, exclude_user_id=member.id)
        member.password_hash = hash_pin(payload.pin)
    db.commit()
    db.refresh(member)
    return _to_read(member, _assigned_counts(db))


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(
    member_id: int,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> None:
    """Removes a member's login. Their assigned tasks stay (assignee just
    clears via the FK); their completion history is removed with them.
    The last remaining owner can never be removed — the household must
    always have an adult who can get in."""
    member = _get_member(db, member_id)
    if member.role == "owner":
        owner_count = db.scalar(
            select(func.count(User.id)).where(User.role == "owner")
        )
        if owner_count <= 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "That's the only adult login — add another before removing this one",
            )
    db.delete(member)
    db.commit()
