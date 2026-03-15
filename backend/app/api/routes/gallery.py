"""
Public gallery endpoint — no auth required.

Returns pre-generated sample plans for the SEO acquisition funnel.
Results are cached in module-level memory after first run.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from app.engine.boq import QuantityEngine
from app.engine.generator import generate
from app.engine.models import PlotConfig

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Gallery presets ────────────────────────────────────────────────────────────
# Dimensions are in metres (converted from ft: 1 ft ≈ 0.3048 m)
# 20 ft = 6.096 m ≈ 6.1 m, 30 ft = 9.144 m ≈ 9.1 m, 40 ft = 12.19 m ≈ 12.2 m, etc.

GALLERY_PRESETS: list[dict[str, Any]] = [
    {
        "id": "20x30-2bhk",
        "name": "20×30 2BHK",
        "plot_length": 9.1,
        "plot_width": 6.1,
        "num_bedrooms": 2,
        "num_toilets": 2,
        "parking": False,
        "city": "Generic",
        "municipality": None,
    },
    {
        "id": "20x40-2bhk",
        "name": "20×40 2BHK",
        "plot_length": 12.2,
        "plot_width": 6.1,
        "num_bedrooms": 2,
        "num_toilets": 2,
        "parking": True,
        "city": "Generic",
        "municipality": None,
    },
    {
        "id": "30x40-3bhk",
        "name": "30×40 3BHK",
        "plot_length": 12.2,
        "plot_width": 9.1,
        "num_bedrooms": 3,
        "num_toilets": 2,
        "parking": True,
        "city": "Generic",
        "municipality": None,
    },
    {
        "id": "30x50-3bhk",
        "name": "30×50 3BHK",
        "plot_length": 15.2,
        "plot_width": 9.1,
        "num_bedrooms": 3,
        "num_toilets": 3,
        "parking": True,
        "city": "Generic",
        "municipality": None,
    },
    {
        "id": "40x40-3bhk",
        "name": "40×40 3BHK",
        "plot_length": 12.2,
        "plot_width": 12.2,
        "num_bedrooms": 3,
        "num_toilets": 3,
        "parking": True,
        "city": "Generic",
        "municipality": None,
    },
    {
        "id": "40x60-4bhk",
        "name": "40×60 4BHK",
        "plot_length": 18.3,
        "plot_width": 12.2,
        "num_bedrooms": 4,
        "num_toilets": 3,
        "parking": True,
        "city": "Generic",
        "municipality": None,
    },
    {
        "id": "20x30-2bhk-chennai",
        "name": "20×30 2BHK Chennai",
        "plot_length": 9.1,
        "plot_width": 6.1,
        "num_bedrooms": 2,
        "num_toilets": 2,
        "parking": False,
        "city": "Chennai",
        "municipality": "Chennai (CMDA)",
    },
    {
        "id": "30x40-3bhk-bangalore",
        "name": "30×40 3BHK Bangalore",
        "plot_length": 12.2,
        "plot_width": 9.1,
        "num_bedrooms": 3,
        "num_toilets": 2,
        "parking": True,
        "city": "Bangalore",
        "municipality": "Bangalore (BBMP)",
    },
]

# Module-level cache: preset_id → serialised plan dict
_cache: dict[str, dict[str, Any]] = {}

_boq_engine = QuantityEngine()

# Cost variance factor for the range display (e.g. 0.90–1.10 of estimate)
_COST_LOW_FACTOR = 0.90
_COST_HIGH_FACTOR = 1.10


def _metres_to_ft(m: float) -> float:
    return round(m / 0.3048)


def _sqm_to_sqft(sqm: float) -> float:
    return round(sqm * 10.764)


def _build_plan(preset: dict[str, Any]) -> dict[str, Any]:
    """Run the generator for one preset and return the serialised gallery card."""
    cfg = PlotConfig(
        plot_length=preset["plot_length"],
        plot_width=preset["plot_width"],
        setback_front=1.0,
        setback_rear=1.0,
        setback_left=0.6,
        setback_right=0.6,
        num_bedrooms=preset["num_bedrooms"],
        toilets=preset["num_toilets"],
        parking=preset["parking"],
        city=preset["city"],
        municipality=preset.get("municipality"),
        road_side="S",
        road_width_m=9.0,
    )

    layouts = generate(cfg)
    if not layouts:
        return {}

    # Pick the best layout (highest score, or first if no scores)
    best = max(layouts, key=lambda lay: lay.score.total if lay.score else 0)

    # BOQ for total cost estimate
    try:
        boq = _boq_engine.calculate(best, cfg, project_name=preset["name"], city="Generic")
        total_cost = boq.total_cost
    except Exception:
        total_cost = 0.0

    gf = best.ground_floor
    plot_area_sqft = _sqm_to_sqft(preset["plot_length"] * preset["plot_width"])
    plot_w_ft = _metres_to_ft(preset["plot_width"])
    plot_l_ft = _metres_to_ft(preset["plot_length"])

    # Determine BHK label
    bhk = preset["num_bedrooms"]
    bhk_label = f"{bhk}BHK"

    # Build city label for display
    city = preset["city"]

    return {
        "id": preset["id"],
        "name": preset["name"],
        "plot_width_m": preset["plot_width"],
        "plot_length_m": preset["plot_length"],
        "plot_width_ft": plot_w_ft,
        "plot_length_ft": plot_l_ft,
        "plot_area_sqft": plot_area_sqft,
        "num_bedrooms": bhk,
        "bhk_label": bhk_label,
        "num_toilets": preset["num_toilets"],
        "parking": preset["parking"],
        "city": city,
        "municipality": preset.get("municipality"),
        "layout_id": best.id,
        "layout_name": best.name,
        "compliance_passed": best.compliance.passed,
        "score": best.score.total if best.score else None,
        "estimated_cost_low": round(total_cost * _COST_LOW_FACTOR),
        "estimated_cost_high": round(total_cost * _COST_HIGH_FACTOR),
        "rooms": [
            {
                "id": r.id,
                "name": r.name,
                "type": r.type,
                "x": r.x,
                "y": r.y,
                "width": r.width,
                "depth": r.depth,
                "area": r.area,
            }
            for r in gf.rooms
        ],
        "columns": [{"x": c.x, "y": c.y} for c in gf.columns],
        "floor": gf.floor,
        "floor_type": gf.floor_type,
        "needs_mech_ventilation": gf.needs_mech_ventilation,
    }


def _get_all_plans() -> list[dict[str, Any]]:
    """Return cached gallery plans, building any that are not yet cached."""
    plans: list[dict[str, Any]] = []
    for preset in GALLERY_PRESETS:
        pid = preset["id"]
        if pid not in _cache:
            try:
                result = _build_plan(preset)
                if result:
                    _cache[pid] = result
                    logger.info("Gallery: built plan %s", pid)
                else:
                    logger.warning("Gallery: generator returned empty layouts for %s", pid)
                    continue
            except Exception as exc:
                logger.warning("Gallery: failed to build plan %s: %s", pid, exc)
                continue
        if pid in _cache:
            plans.append(_cache[pid])
    return plans


@router.get("/gallery/plans")
async def list_gallery_plans() -> list[dict[str, Any]]:
    """Return all pre-generated sample plans for the public gallery."""
    return _get_all_plans()
