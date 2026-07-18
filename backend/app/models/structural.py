"""Stage 2 structural-design lifecycle tables.

ArchitecturalRevision is an immutable snapshot created the moment a user
APPROVES a layout ("preliminary — for planning only" until then); a
StructuralDesign row hangs off one revision. Lifecycle is derived, never
stored on the layout: Draft (no revision matches the current geometry hash)
-> Approved (matching revision) -> Designed (design row on that revision).
Geometry edits mark dependent designs stale via layout_store's edit paths.

db-migration-safe gate (2026-07-17) requirements baked in: explicit
ondelete='CASCADE' on both FKs (Drizzle's user->project cascade chains
through here — create_all never retrofits FKs), JSONB (not generic json)
on Postgres, approved_by is a PLAIN string (never an FK into the
Drizzle-owned 'user' table), and FK columns are indexed (Postgres does not
auto-index FK columns).
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import JSON, DateTime

from app.db import Base

# JSONB on Postgres; plain JSON on the SQLite test database.
_JSONB = JSON().with_variant(JSONB(), "postgresql")


class ArchitecturalRevision(Base):
    __tablename__ = "architectural_revisions"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    layout_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # Immutable LayoutOut-shaped snapshot taken at approval time.
    geometry: Mapped[dict] = mapped_column(_JSONB, nullable=False)
    geometry_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Nullable per db-migration-safe: relaxing NOT NULL later would need
    # manual ALTER on Neon (no Alembic). In practice set on every insert.
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StructuralDesign(Base):
    __tablename__ = "structural_designs"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    revision_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("architectural_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # "designed" | "designed_with_warnings" | "stale" | "superseded"
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="designed")
    # Snapshot of `status` taken the moment a geometry edit staled this design,
    # so reverting the geometry back to a previously-approved revision can
    # resurrect the design to exactly its pre-stale state. Null when live or
    # when staled before this column existed (auto-migrate adds it nullable).
    pre_stale_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    iterations_used: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Post-loop geometry when the design loop adjusted the layout (2.4);
    # null when the approved geometry designed as-is.
    final_geometry: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    structapi_request: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    structapi_response: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    changelog: Mapped[list | None] = mapped_column(_JSONB, nullable=True)
    artifacts_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
