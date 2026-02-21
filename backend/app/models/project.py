import uuid

from sqlalchemy import Boolean, Float, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.db import Base


class Project(Base):
    __tablename__ = "project"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, nullable=False)

    name: Mapped[str] = mapped_column(String, nullable=False)

    # Plot dimensions (metres, 3 dp for feet→m conversion precision)
    plot_length: Mapped[float] = mapped_column(Numeric(7, 3), nullable=False)
    plot_width:  Mapped[float] = mapped_column(Numeric(7, 3), nullable=False)

    # Setbacks (metres, 3 dp)
    setback_front: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    setback_rear:  Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    setback_left:  Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    setback_right: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)

    # Orientation
    road_side:       Mapped[str] = mapped_column(String(1), nullable=False)
    north_direction: Mapped[str] = mapped_column(String(1), nullable=False)

    # Configuration
    num_bedrooms: Mapped[int]  = mapped_column(Integer, nullable=False)
    toilets:      Mapped[int]  = mapped_column(Integer, nullable=False)
    parking:      Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Extended fields (nullable for backward compat with existing rows)
    city:          Mapped[str]   = mapped_column(String(32), default="other", nullable=False,
                                                  server_default="other")
    vastu_enabled: Mapped[bool]  = mapped_column(Boolean, default=False, nullable=False,
                                                   server_default=text("false"))
    road_width_m:  Mapped[float] = mapped_column(Float, default=9.0, nullable=False,
                                                   server_default=text("9.0"))
    has_pooja:   Mapped[bool] = mapped_column(Boolean, default=False, nullable=False,
                                               server_default=text("false"))
    has_study:   Mapped[bool] = mapped_column(Boolean, default=False, nullable=False,
                                               server_default=text("false"))
    has_balcony: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False,
                                               server_default=text("false"))

    # Trapezoid plot support
    plot_shape:       Mapped[str]            = mapped_column(String(20), default="rectangular",
                                                              nullable=False, server_default="rectangular")
    plot_front_width: Mapped[float | None]   = mapped_column(Numeric(8, 3), nullable=True)
    plot_rear_width:  Mapped[float | None]   = mapped_column(Numeric(8, 3), nullable=True)
    plot_side_offset: Mapped[float | None]   = mapped_column(Numeric(8, 3), nullable=True)

    # Multi-floor support (Phase E)
    num_floors:   Mapped[int]  = mapped_column(Integer, default=1, nullable=False,
                                                server_default=text("1"))
    has_stilt:    Mapped[bool] = mapped_column(Boolean, default=False, nullable=False,
                                                server_default=text("false"))
    has_basement: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False,
                                                server_default=text("false"))

    # Arbitrary room config JSON (Phase C)
    custom_room_config: Mapped[str | None]   = mapped_column(
        String, nullable=True)   # JSON array of CustomRoomSpec

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
