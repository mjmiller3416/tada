from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Zone(Base):
    """FlyLady zone (SPEC §6). Phase 1 creates the schema only — the zone
    overlay feature (zone→room mapping UI, "this week's zone") is Phase 3."""

    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    week_of_month: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..5
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
