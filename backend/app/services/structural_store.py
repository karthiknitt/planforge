"""Persistence + lifecycle derivation for Stage 2 structural design.

Lifecycle is DERIVED from data, never stored on the layout:
- draft:    no ArchitecturalRevision matches the current geometry hash
- approved: a matching revision exists, no live design on it
- designed / designed_with_warnings: from the latest non-stale design row
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.structural import ArchitecturalRevision, StructuralDesign


def geometry_hash(geometry: dict) -> str:
    return hashlib.sha256(json.dumps(geometry, sort_keys=True).encode()).hexdigest()


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
    stale. Does NOT commit — callers own the transaction (layout_store's
    edit paths commit once for the edit + invalidation together)."""
    rev_ids = select(ArchitecturalRevision.id).where(
        ArchitecturalRevision.project_id == project_id
    )
    if layout_key is not None:
        rev_ids = rev_ids.where(ArchitecturalRevision.layout_key == layout_key)
    result = await db.execute(
        update(StructuralDesign)
        .where(
            StructuralDesign.revision_id.in_(rev_ids),
            StructuralDesign.status != "stale",
        )
        .values(status="stale")
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
