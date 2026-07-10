from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.db import Base


class UndoStack(Base):
    """Persisted agent undo stack (Task 11), replacing rooms.py's in-memory
    _undo_stacks dict — Cloud Run scales to zero and runs multiple instances,
    so process-local state was lost/inconsistent across requests."""

    __tablename__ = "undo_stacks"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    stack: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
