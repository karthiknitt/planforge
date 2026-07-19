"""Plinth beam design: group wall spans, compute wall-UDL, design via
structapi's generic /v1/calc/beam (NOT the slab-driven /v1/design/building
chain -- see app/engine/plinth_loads.py for why plinth beams need a
different load case than roof beams).

`calc_beam()` can raise `StructuralAPIError` (network/HTTP failure); it is
intentionally left unhandled here -- the caller (the structural export
route, a later task) is expected to map it to an HTTP 502, mirroring the
existing pattern in app/api/routes/structural.py.
"""

from __future__ import annotations

import math

from app.engine.cad_elements import WallSegment
from app.engine.plinth_loads import wall_udl_kn_m
from app.services import structagent_client

FCK_DEFAULT = 20.0  # M20, matches the reference set's "GRADE OF CONCRETE = M20"
FY_DEFAULT = 500.0
CEILING_HEIGHT_M = 2.75  # compliance_rules.json min_habitable_ceiling_m proxy


def _group_key(w: WallSegment) -> tuple[str, float]:
    # Grouped by (kind, rounded length) -- NOT by w.thickness. Wall thickness
    # is standardized by kind (230mm external / 115mm internal, matching
    # compliance_rules.json) rather than read per-instance from geometry, so
    # two walls of the same kind and span always share one beam design even
    # if their drawn thickness differs slightly.
    return (w.kind, round(w.length, 1))


def _trial_depth_mm(span_m: float) -> int:
    """L/12 thumb-rule trial depth, rounded up to nearest 25mm."""
    return int(math.ceil((span_m * 1000.0 / 12.0) / 25.0)) * 25


async def design_plinth_beams(
    walls: list[WallSegment],
    *,
    external_thickness_mm: float = 230,
    internal_thickness_mm: float = 115,
    fck: float = FCK_DEFAULT,
    fy: float = FY_DEFAULT,
) -> dict[str, dict]:
    """Group wall spans, design one beam per unique (kind, span) group.

    Returns {"plinth-{kind}-span{span_m:.2f}": {..calc_beam data.., "span_m":,
    "kind":, "b_mm":, "D_mm":}} -- keyed by kind AND span (not span alone) so
    an external wall and an internal wall that happen to share the same
    rounded length don't collide on the same output key -- same
    key-per-unique-group shape as structapi's roof-beam `data.beams`, so the
    drawing renderer can treat both uniformly.
    """
    groups: dict[tuple[str, float], list[WallSegment]] = {}
    for w in walls:
        groups.setdefault(_group_key(w), []).append(w)

    out: dict[str, dict] = {}
    for (kind, span_m), members in groups.items():
        if span_m <= 0:
            continue
        thickness_mm = (
            external_thickness_mm if kind == "external" else internal_thickness_mm
        )
        w_dl = wall_udl_kn_m(thickness_mm=thickness_mm, height_m=CEILING_HEIGHT_M)
        D = _trial_depth_mm(span_m)
        result = await structagent_client.calc_beam(
            {
                "span_m": span_m,
                "w_dl_kn_m": w_dl,
                "w_il_kn_m": 0.0,
                "b": thickness_mm,
                "D": D,
                "fck": fck,
                "fy": fy,
                "support": "ss",
            }
        )
        key = f"plinth-{kind}-span{span_m:.2f}"
        out[key] = {
            "b_mm": thickness_mm,
            "D_mm": D,
            "span_m": span_m,
            "kind": kind,
            "count": len(members),
            "ok": result.ok,
            "design": (result.data or {}).get("design", {}),
            "checks": result.checks,
        }
    return out
