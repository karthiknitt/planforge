"""Persistence + lifecycle derivation for Stage 2 structural design.

Lifecycle is DERIVED from data, never stored on the layout:
- draft:    no ArchitecturalRevision matches the current geometry hash
- approved: a matching revision exists, no live design on it
- designed / designed_with_warnings: from the latest non-stale design row
"""

from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.structural import ArchitecturalRevision, StructuralDesign

logger = logging.getLogger(__name__)

_FLOOR_KEYS = ("ground_floor", "first_floor", "second_floor", "basement_floor")
_ROOM_FIELDS = ("id", "type", "x", "y", "width", "depth")


def _canonical_room(room: dict) -> dict:
    return {field: room.get(field) for field in _ROOM_FIELDS}


def _canonical_geometry(geometry: dict) -> dict:
    """Rooms-only canonical structure for hashing.

    Deliberately excludes everything except (id, type, x, y, width, depth)
    per room, keyed by floor number. Derived fields (compliance, score,
    space_notes) and columns (derived from rooms) are excluded on purpose:
    including them re-breaks approvals whenever the scorer, compliance
    engine, or column-derivation logic changes without the rooms actually
    moving.
    """
    floors = []
    for key in _FLOOR_KEYS:
        floor_data = geometry.get(key) if isinstance(geometry, dict) else None
        if not floor_data:
            continue
        rooms = floor_data.get("rooms") or []
        canonical_rooms = sorted(
            (_canonical_room(r) for r in rooms if isinstance(r, dict)),
            key=lambda r: str(r.get("id")),
        )
        floors.append({"floor": floor_data.get("floor"), "rooms": canonical_rooms})
    floors.sort(key=lambda f: (f["floor"] is None, f["floor"]))
    return {"floors": floors}


def geometry_hash(geometry: dict) -> str:
    canonical = _canonical_geometry(geometry or {})
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


async def rehash_architectural_revisions(db: AsyncSession) -> int:
    """One-time (idempotent) startup migration: recompute every stored
    geometry_hash with the current rooms-only algorithm and update rows
    whose hash has drifted (e.g. rows hashed under the old whole-dict
    algorithm). Safe to run on every boot — a no-op once all rows match."""
    result = await db.execute(select(ArchitecturalRevision))
    revisions = list(result.scalars().all())
    updated = 0
    for rev in revisions:
        try:
            new_hash = geometry_hash(rev.geometry)
        except Exception:
            logger.warning(
                "rehash_architectural_revisions: skipping revision %s — "
                "malformed geometry",
                rev.id,
            )
            continue
        if new_hash != rev.geometry_hash:
            rev.geometry_hash = new_hash
            updated += 1
    if updated:
        await db.commit()
    return updated


async def find_revision_for_hash(
    project_id: str, layout_key: str, ghash: str, db: AsyncSession
) -> ArchitecturalRevision | None:
    result = await db.execute(
        select(ArchitecturalRevision)
        .where(
            ArchitecturalRevision.project_id == project_id,
            ArchitecturalRevision.layout_key == layout_key,
            ArchitecturalRevision.geometry_hash == ghash,
        )
        .order_by(ArchitecturalRevision.approved_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def approve_layout(
    project_id: str,
    layout_key: str,
    geometry: dict,
    user_id: str,
    db: AsyncSession,
) -> tuple[ArchitecturalRevision, bool]:
    """Create the immutable approval snapshot. Idempotent: re-approving the
    same geometry returns the existing revision (created=False, no-op)."""
    ghash = geometry_hash(geometry)
    existing = await find_revision_for_hash(project_id, layout_key, ghash, db)
    if existing is not None:
        return existing, False
    rev = ArchitecturalRevision(
        project_id=project_id,
        layout_key=layout_key,
        geometry=geometry,
        geometry_hash=ghash,
        approved_by=user_id,
    )
    db.add(rev)
    await db.commit()
    await db.refresh(rev)
    return rev, True


async def latest_design(revision_id: str, db: AsyncSession) -> StructuralDesign | None:
    result = await db.execute(
        select(StructuralDesign)
        .where(
            StructuralDesign.revision_id == revision_id,
            StructuralDesign.status != "stale",
        )
        .order_by(StructuralDesign.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def persist_design(
    revision: ArchitecturalRevision,
    db: AsyncSession,
    *,
    status: str,
    iterations_used: int = 1,
    structapi_request: dict | None = None,
    structapi_response: dict | None = None,
    changelog: list | None = None,
    final_geometry: dict | None = None,
    artifacts_ref: str | None = None,
) -> StructuralDesign:
    design = StructuralDesign(
        revision_id=revision.id,
        status=status,
        iterations_used=iterations_used,
        structapi_request=structapi_request,
        structapi_response=structapi_response,
        changelog=changelog,
        final_geometry=final_geometry,
        artifacts_ref=artifacts_ref,
    )
    db.add(design)
    await db.commit()
    await db.refresh(design)
    return design


async def mark_designs_stale(
    project_id: str, db: AsyncSession, layout_key: str | None = None
) -> int:
    """Mark every live design under this project (optionally one layout)
    stale, recording the prior status in pre_stale_status so a later revert
    to the same geometry can resurrect it. Does NOT commit — callers own the
    transaction (layout_store's edit paths commit once for the edit +
    invalidation together).

    `superseded` designs are intentionally left untouched (they are already
    retired and must stay that way), as are rows already `stale`.
    """
    rev_ids = select(ArchitecturalRevision.id).where(
        ArchitecturalRevision.project_id == project_id
    )
    if layout_key is not None:
        rev_ids = rev_ids.where(ArchitecturalRevision.layout_key == layout_key)
    result = await db.execute(
        update(StructuralDesign)
        .where(
            StructuralDesign.revision_id.in_(rev_ids),
            StructuralDesign.status.not_in(("stale", "superseded")),
        )
        # pre_stale_status references the OLD status value (standard SQL
        # UPDATE semantics — every SET reads the pre-update row).
        .values(pre_stale_status=StructuralDesign.status, status="stale")
    )
    return result.rowcount or 0


async def resurrect_designs_for_revision(revision_id: str, db: AsyncSession) -> int:
    """Un-stale designs tied to `revision_id`, restoring each to its recorded
    pre_stale_status. Called when a geometry edit lands back on a
    previously-approved revision's hash, so an identical geometry never forces
    a re-run of an expensive structural design. Does NOT commit — the caller
    owns the edit transaction.

    Only rows currently `stale` are affected; `superseded` rows are never
    touched. Rows staled before pre_stale_status existed (null) fall back to
    the conservative `designed_with_warnings`.
    """
    result = await db.execute(
        update(StructuralDesign)
        .where(
            StructuralDesign.revision_id == revision_id,
            StructuralDesign.status == "stale",
        )
        .values(
            status=func.coalesce(
                StructuralDesign.pre_stale_status, "designed_with_warnings"
            ),
            pre_stale_status=None,
        )
    )
    return result.rowcount or 0


async def design_surface(
    project_id: str, layout_key: str, geometry: dict, db: AsyncSession
) -> dict | None:
    """Latest non-stale StructuralDesign for the layout's CURRENT approved
    revision, shaped for drawing/BOQ/API consumers. None when unapproved or
    undesigned -- callers treat that as "no structural set" (preliminary /
    estimated fallback)."""
    revision = await find_revision_for_hash(
        project_id, layout_key, geometry_hash(geometry), db
    )
    if revision is None:
        return None
    design = await latest_design(revision.id, db)
    if design is None:
        return None
    response = design.structapi_response or {}
    return {
        "design_id": design.id,
        "revision_id": revision.id,
        "status": design.status,
        "iterations_used": design.iterations_used,
        "changelog": design.changelog or [],
        "final_geometry": design.final_geometry,
        "structapi": {
            "checks": response.get("checks"),
            "data": response.get("data"),
            "disclaimer": response.get("disclaimer"),
        },
        "created_at": design.created_at.isoformat() if design.created_at else None,
    }


async def layout_status(
    project_id: str, layout_key: str, geometry: dict, db: AsyncSession
) -> dict:
    ghash = geometry_hash(geometry)
    rev = await find_revision_for_hash(project_id, layout_key, ghash, db)
    if rev is None:
        return {
            "layout_id": layout_key,
            "status": "draft",
            "geometry_hash": ghash,
            "revision_id": None,
            "design": None,
        }
    design = await latest_design(rev.id, db)
    return {
        "layout_id": layout_key,
        "status": design.status if design else "approved",
        "geometry_hash": ghash,
        "revision_id": rev.id,
        "design": None
        if design is None
        else {
            "id": design.id,
            "status": design.status,
            "iterations_used": design.iterations_used,
            "created_at": design.created_at.isoformat(),
            "changelog": design.changelog,
        },
    }
