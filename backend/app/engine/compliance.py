from __future__ import annotations

import json
from pathlib import Path

from .models import ComplianceResult, Layout, PlotConfig, RoomType

_RULES_PATH = Path(__file__).parent.parent / "config" / "compliance_rules.json"
_CITY_PATH  = Path(__file__).parent.parent / "config" / "city_rules.json"


def load_rules() -> dict:
    return json.loads(_RULES_PATH.read_text())


def load_city_rules() -> dict:
    return json.loads(_CITY_PATH.read_text())


def get_city_setbacks(city: str, plot_area: float, city_data: dict) -> dict | None:
    """Look up setback defaults for a city based on plot area. Returns None if city not found."""
    city_key = city.lower().strip()
    if city_key not in city_data:
        city_key = "other"
    table = city_data[city_key].get("setback_table", [])
    for row in table:
        if plot_area <= row["plot_area_max_sqm"]:
            return row
    return table[-1] if table else None


def get_city_far(city: str, road_width_m: float, city_data: dict) -> float | None:
    """Look up FAR limit for a city + road width combination."""
    city_key = city.lower().strip()
    if city_key not in city_data:
        city_key = "other"
    table = city_data[city_key].get("far_by_road_width", [])
    for row in table:
        if road_width_m <= row["road_width_max_m"]:
            return row["far"]
    return None


def check(layout: Layout, cfg: PlotConfig, rules: dict | None = None) -> ComplianceResult:
    if rules is None:
        rules = load_rules()

    city_data = load_city_rules()
    violations: list[str] = []
    warnings: list[str] = []

    # --- Minimum plot dimensions ---
    min_length = rules["min_plot_length_m"]
    min_width  = rules["min_plot_width_m"]
    if cfg.plot_length < min_length:
        violations.append(f"Plot length {cfg.plot_length} m is below minimum {min_length} m")
    if cfg.plot_width < min_width:
        violations.append(f"Plot width {cfg.plot_width} m is below minimum {min_width} m")

    all_rooms = layout.ground_floor.rooms + layout.first_floor.rooms

    # --- Minimum room areas ---
    min_bed     = rules["min_bedroom_sqm"]
    min_bed_w   = rules["min_bedroom_width_m"]
    min_kit     = rules["min_kitchen_sqm"]
    min_kit_w   = rules["min_kitchen_width_m"]
    min_wc      = rules["min_toilet_sqm"]
    min_wc_w    = rules["min_toilet_width_m"]
    min_stair_w = rules["min_stair_width_mm"] / 1000

    for room in all_rooms:
        if room.type == "bedroom":
            if room.area < min_bed:
                violations.append(
                    f"{room.name}: {room.area:.1f} sqm < {min_bed} sqm minimum (NBC)"
                )
            if min(room.width, room.depth) < min_bed_w:
                warnings.append(
                    f"{room.name}: width {min(room.width, room.depth):.2f} m "
                    f"< {min_bed_w} m recommended (NBC 2.4 m habitable)"
                )

        if room.type == "kitchen":
            if room.area < min_kit:
                violations.append(
                    f"{room.name}: {room.area:.1f} sqm < {min_kit} sqm minimum (NBC)"
                )
            if min(room.width, room.depth) < min_kit_w:
                warnings.append(
                    f"{room.name}: width {min(room.width, room.depth):.2f} m "
                    f"< {min_kit_w} m recommended (NBC)"
                )

        if room.type == "toilet":
            if room.area < min_wc:
                violations.append(
                    f"{room.name}: {room.area:.1f} sqm < {min_wc} sqm minimum (NBC)"
                )
            if min(room.width, room.depth) < min_wc_w:
                warnings.append(
                    f"{room.name}: width {min(room.width, room.depth):.2f} m "
                    f"< {min_wc_w} m recommended (NBC)"
                )

    # --- Staircase width ---
    for room in all_rooms:
        if room.type == "staircase":
            if room.width < min_stair_w and room.depth < min_stair_w:
                violations.append(
                    f"Staircase clear width {room.width:.2f} m < {min_stair_w} m minimum (NBC)"
                )

    # --- Beam span (ground floor) ---
    max_span = rules["max_beam_span_m"]
    for room in layout.ground_floor.rooms:
        if room.width > max_span:
            warnings.append(
                f"{room.name}: span {room.width:.1f} m > {max_span} m — add intermediate beam"
            )

    # --- Floor coverage ---
    buildable_w = cfg.plot_width  - cfg.setback_left  - cfg.setback_right
    buildable_d = cfg.plot_length - cfg.setback_front - cfg.setback_rear
    footprint   = buildable_w * buildable_d
    plot_area   = cfg.plot_width * cfg.plot_length
    coverage_pct = (footprint / plot_area) * 100

    max_cov = rules["max_floor_coverage_pct"]
    if coverage_pct > max_cov:
        violations.append(
            f"Floor coverage {coverage_pct:.1f}% > {max_cov}% maximum — increase setbacks"
        )

    # --- FAR check (city-aware) ---
    total_built = footprint * 2  # G+1 → two floors
    far_limit = get_city_far(cfg.city, cfg.road_width_m, city_data)
    if far_limit is None:
        far_limit = rules.get("default_far", 1.5)
    actual_far = total_built / plot_area
    if actual_far > far_limit + 0.01:
        warnings.append(
            f"FAR {actual_far:.2f} exceeds city limit {far_limit:.2f} for {cfg.city.title()} "
            f"(road width {cfg.road_width_m} m)"
        )

    # --- Room boundary vs. setback lines ---
    ewt = rules["external_wall_thickness_mm"] / 1000
    min_x = cfg.setback_left  + ewt
    max_x = cfg.plot_width    - cfg.setback_right - ewt
    min_y = cfg.setback_front + ewt
    max_y = cfg.plot_length   - cfg.setback_rear  - ewt
    tol   = 0.005  # 5 mm floating-point tolerance
    for room in all_rooms:
        if room.x < min_x - tol or room.x + room.width > max_x + tol:
            violations.append(f"{room.name} extends outside horizontal setback boundary")
        if room.y < min_y - tol or room.y + room.depth > max_y + tol:
            violations.append(f"{room.name} extends outside vertical setback boundary")

    # --- Window/ventilation warnings (informational only) ---
    min_win_ratio = rules.get("min_window_to_floor_ratio", 0.1)
    for room in all_rooms:
        if room.type in ("bedroom", "living", "study", "dining"):
            required_win = room.area * min_win_ratio
            warnings.append(
                f"{room.name}: provide ≥ {required_win:.2f} sqm window opening (NBC 1/10th floor area)"
            ) if room.area < 10 else None  # only warn for small rooms as a hint

    return ComplianceResult(
        passed=len(violations) == 0,
        violations=violations,
        warnings=warnings,
    )
