import uuid

from sqlalchemy import Boolean, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.db import Base


class Project(Base):
    __tablename__ = "project"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, nullable=False)  # FK enforced at DB level by Drizzle
    name: Mapped[str] = mapped_column(String, nullable=False)

    # Plot dimensions (metres, 3 dp for feet→m conversion precision)
    plot_length: Mapped[float] = mapped_column(Numeric(7, 3), nullable=False)
    plot_width: Mapped[float] = mapped_column(Numeric(7, 3), nullable=False)

    # Setbacks (metres, 3 dp)
    setback_front: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    setback_rear: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    setback_left: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    setback_right: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)

    # Orientation
    road_side: Mapped[str] = mapped_column(String(1), nullable=False)
    north_direction: Mapped[str] = mapped_column(String(1), nullable=False)

    # Configuration
    bhk: Mapped[int] = mapped_column(Integer, nullable=False)
    toilets: Mapped[int] = mapped_column(Integer, nullable=False)
    parking: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
