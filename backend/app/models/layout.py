import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.db import Base


class StoredLayout(Base):
    """The canonical persisted geometry for one generated (or edited) layout.

    Before this table existed every consumer (viewer, share view, PDF/DXF/BOQ
    exports, revisions, agent chat) re-ran the CP-SAT solver independently —
    the user could edit one thing and export another.

    `geometry` is the LayoutOut-shaped dict (rooms/columns per floor,
    compliance, score) — the same JSON the API already speaks.
    """

    __tablename__ = "layouts"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # CASCADE required: Drizzle's user->project cascade otherwise hits FK
    # violations when a Better Auth user is deleted (db-migration-safe gate).
    project_id: Mapped[str] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The engine-facing id ("solver-front-0", "A", ...) the frontend already
    # uses as layout_id in export/compare URLs. Unique per project.
    layout_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="solver"
    )  # "solver" | "edited"
    geometry: Mapped[dict] = mapped_column(JSON, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
