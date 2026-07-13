import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.db import Base


class GenerationJob(Base):
    """Tracks an async layout/render job (Task 3/4/6) so the frontend can poll
    status instead of blocking a request on the CP-SAT solver or AI render call."""

    __tablename__ = "generation_jobs"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="layout")
    layout_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional R3F 3D snapshot (PNG) sent by the frontend to condition the
    # render on exact geometry instead of the rasterised 2D PDF plan.
    reference_png: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    # Floor the render job targets (geometry dict key); render jobs only.
    render_floor: Mapped[str | None] = mapped_column(String(24), nullable=True)
    requested_by: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
