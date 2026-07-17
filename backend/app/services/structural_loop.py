"""Closed-loop structural design orchestrator (Stage 2.4).

approved geometry -> grid -> structapi design -> on span violations,
re-constrain the solver (tighter span caps force an extra aligned wall /
grid line) and re-solve with drift minimised against the approved plan.
Capped at MAX_ITERATIONS; on exhaustion the last design is persisted as
"designed_with_warnings" rather than failing.

The stored layout is NEVER overwritten: it stays the architectural set
(matching the approved revision's hash). The loop's adjusted geometry
lands in StructuralDesign.final_geometry — the structural set that
drawings/BOQ consume when present — with a deterministic changelog of
what moved vs the approved plan and why.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine import solver
from app.engine.models import Layout
from app.engine.structural_grid import extract_grid
from app.models.project import Project
from app.models.structural import ArchitecturalRevision, StructuralDesign
from app.services import layout_store, structagent_client, structural_store
from app.services.plot_config import plot_config_from_project

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 3
#: shrink applied on top of the limit/actual ratio so the re-solved span
#: clears the failed check with margin instead of landing exactly on it
_CAP_MARGIN = 0.95
#: remedy hints that a re-solve can address (everything else — materials,
#: bearing capacity, detailing — is a user-input change, never automated)
_RESOLVABLE = {"reduce_span", "add_grid_line"}

#: geometry deltas below this are float noise, not changelog-worthy
_DIFF_EPS = 0.05


class GridNotExtractable(Exception):
    def __init__(self, notes: list[str]):
        self.notes = notes
        super().__init__("no structural grid")


def cap_from_violation(v: dict) -> float | None:
    """Target span cap (metres) for one resolvable violation."""
    span = v.get("span_m")
    if not span:
        return None
    if v.get("remedy_hint") == "add_grid_line":
        # section iteration maxed out entirely — halve the bay
        return round(span * 0.55, 3)
    actual, limit = v.get("actual"), v.get("limit")
    if actual and limit and actual > 0:
        ratio = min(max(limit / actual, 0.4), _CAP_MARGIN)
        return round(span * ratio, 3)
    return round(span * 0.8, 3)


def diff_rooms(approved: dict, final: dict) -> list[str]:
    """Deterministic human-readable room diff between two geometry dicts."""
    entries: list[str] = []
    for floor_key, label in (("ground_floor", "GF"), ("first_floor", "FF")):
        before = {r["id"]: r for r in (approved.get(floor_key) or {}).get("rooms", [])}
        after = {r["id"]: r for r in (final.get(floor_key) or {}).get("rooms", [])}
        for rid, b in before.items():
            a = after.get(rid)
            if a is None:
                entries.append(f"{label}: {b['name']} removed")
                continue
            moved = abs(a["x"] - b["x"]) > _DIFF_EPS or abs(a["y"] - b["y"]) > _DIFF_EPS
            resized = (
                abs(a["width"] - b["width"]) > _DIFF_EPS
                or abs(a["depth"] - b["depth"]) > _DIFF_EPS
            )
            if resized:
                entries.append(
                    f"{label}: {b['name']} resized "
                    f"{b['width']:.1f}×{b['depth']:.1f} m → "
                    f"{a['width']:.1f}×{a['depth']:.1f} m"
                )
            elif moved:
                entries.append(
                    f"{label}: {b['name']} moved "
                    f"({b['x']:.1f}, {b['y']:.1f}) → ({a['x']:.1f}, {a['y']:.1f})"
                )
        for rid, a in after.items():
            if rid not in before:
                entries.append(f"{label}: {a['name']} added")
    return entries


def _grid_or_raise(geometry: dict):
    ground = (geometry or {}).get("ground_floor") or {}
    grid = extract_grid(ground.get("columns") or [])
    if not grid.x_spacings_m or not grid.y_spacings_m:
        raise GridNotExtractable(grid.notes)
    return grid


def _violation_line(v: dict, cap: float | None) -> str:
    where = v.get("grid_ref") or v.get("member_type", "member")
    line = (
        f"{v.get('check', 'check failed')} at {where}: "
        f"actual {v.get('actual')} vs limit {v.get('limit')} {v.get('unit', '')}"
    ).strip()
    if cap is not None:
        axis = v.get("axis") or "?"
        line += f" — capped room spans along {axis} to {cap} m and re-solved"
    return line


async def run_design_loop(
    project: Project,
    revision: ArchitecturalRevision,
    db: AsyncSession,
    *,
    sbc_kpa: float,
    fck: float,
    fy: float,
    include_pdf: bool,
    city_seismic_zone: dict[str, str],
) -> tuple[StructuralDesign, dict, object]:
    """Run the closed loop. Returns (persisted design, last grid dict,
    last structapi result). Raises GridNotExtractable / StructuralAPIError
    for the route to translate."""
    cfg = plot_config_from_project(project)
    ewt = 0.23  # matches generate()'s external wall thickness convention

    approved_geometry = revision.geometry
    current_geometry = approved_geometry
    span_caps: dict[str, float] = {}
    changelog: list[str] = []
    result = None
    grid = None
    payload: dict = {}

    city = (project.city or "").lower()

    for iteration in range(1, MAX_ITERATIONS + 1):
        grid = _grid_or_raise(current_geometry)
        payload = {
            "grid": {
                "x_spacings_m": grid.x_spacings_m,
                "y_spacings_m": grid.y_spacings_m,
            },
            "storeys": max(int(project.num_floors or 1), 1),
            "occupancy": "residential_room",
            "location": {
                "city": city or None,
                "seismic_zone": city_seismic_zone.get(city, "III"),
            },
            "sbc_kpa": sbc_kpa,
            "materials": {"fck": fck, "fy": fy},
            "options": {"pdf_report": include_pdf},
        }
        result = await structagent_client.design_building(
            payload, correlation_id=f"{project.id}:{revision.layout_key}:i{iteration}"
        )

        violations = (result.data or {}).get("violations") or []
        resolvable = [
            v
            for v in violations
            if v.get("remedy_hint") in _RESOLVABLE and v.get("span_m")
        ]
        if result.ok or not resolvable or iteration == MAX_ITERATIONS:
            if not result.ok and resolvable and iteration == MAX_ITERATIONS:
                changelog.append(
                    f"Iteration cap ({MAX_ITERATIONS}) reached with unresolved "
                    "span violations — design saved with warnings"
                )
            # Log every violation the loop did NOT act on — filtering by
            # remedy_hint alone silently dropped resolvable hints that
            # lacked span_m (excluded from the re-solve list too), leaving
            # a warnings-status design with an empty changelog.
            for v in violations:
                if v not in resolvable:
                    changelog.append(_violation_line(v, None))
            break

        # Tighten span caps from the violations and re-solve, drift-minimised
        for v in resolvable:
            cap = cap_from_violation(v)
            if cap is None:
                continue
            axis = v.get("axis") or "x"
            if cap < span_caps.get(axis, float("inf")):
                span_caps[axis] = cap
                changelog.append(_violation_line(v, cap))

        approved_layout = layout_store.engine_layout_from_geometry(approved_geometry)
        new_layout: Layout | None = solver.resolve_with_constraints(
            cfg, ewt, approved_layout, span_caps
        )
        if new_layout is None:
            changelog.append(
                "Re-solve with structural span caps was infeasible — "
                "keeping last design (with warnings)"
            )
            break
        new_geometry = layout_store.layout_out_from_engine(new_layout).model_dump()
        # keep the approved layout's identity — this is a structural
        # adjustment of the same layout, not a new variant
        new_geometry["id"] = approved_geometry.get("id", revision.layout_key)
        new_geometry["name"] = approved_geometry.get("name", revision.layout_key)
        current_geometry = new_geometry

    assert result is not None and grid is not None  # loop runs at least once

    adjusted = current_geometry is not approved_geometry
    if adjusted:
        changelog.extend(diff_rooms(approved_geometry, current_geometry))

    design_status = "designed" if result.ok else "designed_with_warnings"
    design = await structural_store.persist_design(
        revision,
        db,
        status=design_status,
        iterations_used=iteration,
        structapi_request=payload,
        structapi_response={
            "ok": result.ok,
            "checks": result.checks,
            "data": result.data,
            "disclaimer": result.disclaimer,
        },
        changelog=changelog,
        final_geometry=current_geometry if adjusted else None,
    )
    return design, grid, result
