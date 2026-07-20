from pydantic import BaseModel, Field


class ZoneRoomBrief(BaseModel):
    """A mapped room as it rides along on a zone — enough for the zone
    card and the Settings mapping editor."""

    id: int
    name: str


class ZoneRead(BaseModel):
    id: int
    name: str
    week_of_month: int
    rooms: list[ZoneRoomBrief]


class ZonesResponse(BaseModel):
    """The whole overlay in one call: the five zones with their rooms,
    plus which week (and therefore which zone) today falls in."""

    zones: list[ZoneRead]
    week_of_month: int
    current_zone_id: int | None


class ZoneUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
