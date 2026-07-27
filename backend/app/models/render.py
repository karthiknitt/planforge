"""Cached AI renders per layout geometry-hash."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, deferred, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.db import Base


class LayoutRender(Base):
    __tablename__ = "layout_renders"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    layout_id: Mapped[str] = mapped_column(
        ForeignKey("layouts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    layout_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Which floor of the layout this render depicts (geometry dict key:
    # ground_floor / first_floor / second_floor / basement_floor).
    floor: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="ground_floor",
        server_default="ground_floor",
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    image_png: Mapped[bytes | None] = deferred(
        mapped_column(LargeBinary, nullable=True)
    )
    # R2 object key. Rows written before R2 was enabled keep image_png instead.
    image_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
