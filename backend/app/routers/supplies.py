from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.supply import Supply
from app.models.user import User
from app.routers.auth import require_owner
from app.schemas.supplies import SupplyCreate, SupplyRead, SupplyUpdate, supply_to_read
from app.services import supply_service

router = APIRouter(prefix="/api/supplies", tags=["supplies"])


def _get_supply(db: Session, supply_id: int) -> Supply:
    supply = db.get(Supply, supply_id)
    if supply is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supply not found")
    return supply


@router.get("", response_model=list[SupplyRead])
def list_supplies(
    _: User = Depends(require_owner), db: Session = Depends(get_db)
) -> list[SupplyRead]:
    """The whole (small) inventory — needs-attention first, then A→Z."""
    supplies = db.scalars(select(Supply)).all()
    order = {"out": 0, "low": 1, "in_stock": 2}
    ranked = sorted(supplies, key=lambda s: (order.get(s.status, 3), s.name.lower()))
    return [supply_to_read(s) for s in ranked]


@router.post("", response_model=SupplyRead, status_code=status.HTTP_201_CREATED)
def create_supply(
    payload: SupplyCreate,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> SupplyRead:
    supply = Supply(name=payload.name.strip())
    db.add(supply)
    db.commit()
    db.refresh(supply)
    return supply_to_read(supply)


@router.patch("/{supply_id}", response_model=SupplyRead)
def update_supply(
    supply_id: int,
    payload: SupplyUpdate,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> SupplyRead:
    """Rename and/or the one-tap manual status change (SPEC §6: manual
    only, never auto-decremented). Marking low/out pushes the item into
    Enchanted Spoon's shopping list, deduped per low-run."""
    supply = _get_supply(db, supply_id)
    if payload.name is not None:
        supply.name = payload.name.strip()

    pushed = False
    if payload.status is not None and payload.status != supply.status:
        pushed = supply_service.set_status(supply, payload.status)

    db.commit()
    db.refresh(supply)
    return supply_to_read(supply, pushed=pushed)


@router.delete("/{supply_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supply(
    supply_id: int,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> None:
    """Removes the supply and its task links (the tasks themselves are
    untouched)."""
    supply = _get_supply(db, supply_id)
    db.delete(supply)
    db.commit()
