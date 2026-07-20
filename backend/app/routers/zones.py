from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.room import Room
from app.models.user import User
from app.models.zone import Zone
from app.routers.auth import require_owner
from app.schemas.zones import ZoneRead, ZoneRoomBrief, ZonesResponse, ZoneUpdate
from app.services import zones as zone_service

router = APIRouter(prefix="/api/zones", tags=["zones"])


def _zones_response(db: Session, current_user: User) -> ZonesResponse:
    zones = db.scalars(select(Zone).order_by(Zone.week_of_month)).all()
    rooms = db.scalars(
        select(Room).where(Room.zone_id.is_not(None)).order_by(Room.sort_order, Room.id)
    ).all()
    by_zone: dict[int, list[ZoneRoomBrief]] = {}
    for room in rooms:
        by_zone.setdefault(room.zone_id, []).append(
            ZoneRoomBrief(id=room.id, name=room.name)
        )

    today = zone_service.local_today(db, current_user.id)
    week = zone_service.week_of_month(today)
    current = next((z for z in zones if z.week_of_month == week), None)
    return ZonesResponse(
        zones=[
            ZoneRead(
                id=zone.id,
                name=zone.name,
                week_of_month=zone.week_of_month,
                rooms=by_zone.get(zone.id, []),
            )
            for zone in zones
        ],
        week_of_month=week,
        current_zone_id=current.id if current else None,
    )


@router.get("", response_model=ZonesResponse)
def list_zones(
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> ZonesResponse:
    """The zone overlay state (SPEC §6): the five zones, their mapped
    rooms, and which zone this week belongs to. An empty `zones` list
    means the overlay was never set up."""
    return _zones_response(db, current_user)


@router.post("/setup", response_model=ZonesResponse)
def setup_zones(
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> ZonesResponse:
    """Seed FlyLady's five default zones and auto-map existing rooms by
    name (SPEC §6). Safe to call again — it never duplicates zones or
    moves a room she has already placed."""
    zone_service.seed_default_zones(db)
    db.commit()
    return _zones_response(db, current_user)


@router.patch("/{zone_id}", response_model=ZonesResponse)
def update_zone(
    zone_id: int,
    payload: ZoneUpdate,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> ZonesResponse:
    """Rename a zone ("most homes differ" — SPEC §6). Room mapping moves
    through PATCH /api/rooms/{id} instead, so there's one way to place a
    room."""
    zone = db.get(Zone, zone_id)
    if zone is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Zone not found")
    if payload.name is not None:
        zone.name = payload.name
    db.commit()
    return _zones_response(db, current_user)
