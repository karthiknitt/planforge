from __future__ import annotations

import json
from pathlib import Path

from .models import ComplianceResult, Layout, PlotConfig, RoomType

_RULES_PATH = Path(__file__).parent.parent / "config" / "compliance_rules.json"


def load_rules() -> dict:
    return json.loads(_RULES_PATH.read_text())


def check(layout: Layout, cfg: PlotConfig, rules: dict | None = None) -> ComplianceResult:
    if rules is None:
        rules = load_rules()

    violations: list[str] = []
    warnings: list[str] = []

    all_rooms = layout.ground_floor.rooms + layout.first_floor.rooms

    # --- Minimum room sizes ---
    min_bed = rules["min_bedroom_sqm"]
    min_kit = rules["min_kitchen_sqm"]
    min_wc = rules["min_toilet_sqm"]
    min_stair_w = rules["min_stair_width_mm"] / 1000

    for room in all_rooms:
        if room.type == "bedroom" and room.area < min_bed:
            violations.append(
                f"{room.name}: {room.area:.1f} sqm < {min_bed} sqm minimum"
            )
        if room.type == "kitchen" and room.area < min_kit:
            violations.append(
                f"{room.name}: {room.area:.1f} sqm < {min_kit} sqm minimum"
            )
        if room.type == "toilet" and room.area < min_wc:
            violations.append(
                f"{room.name}: {room.area:.1f} sqm < {min_wc} sqm minimum"
            )

    # --- Staircase width ---
    for room in all_rooms:
        if room.type == "staircase":
            if room.width < min_stair_w and room.depth < min_stair_w:
                violations.append(
                    f"Staircase clear width {room.width:.2f} m < {min_stair_w} m minimum"
                )

    # --- Beam span (ground floor) ---
    max_span = rules["max_beam_span_m"]
    for room in layout.ground_floor.rooms:
        if room.width > max_span:
            warnings.append(
                f"{room.name}: span {room.width:.1f} m > {max_span} m — add intermediate beam"
            )

    # --- Floor coverage ---
    buildable_w = cfg.plot_width - cfg.setback_left - cfg.setback_right
    buildable_d = cfg.plot_length - cfg.setback_front - cfg.setback_rear
    footprint = buildable_w * buildable_d
    plot_area = cfg.plot_width * cfg.plot_length
    coverage_pct = (footprint / plot_area) * 100

    max_cov = rules["max_floor_coverage_pct"]
    if coverage_pct > max_cov:
        violations.append(
            f"Floor coverage {coverage_pct:.1f}% > {max_cov}% maximum — increase setbacks"
        )

    return ComplianceResult(
        passed=len(violations) == 0,
        violations=violations,
        warnings=warnings,
    )
