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

    all_floors = [layout.ground_floor, layout.first_floor]
    if layout.second_floor is not None:
        all_floors.append(layout.second_floor)
    if layout.basement_floor is not None:
        all_floors.append(layout.basement_floor)
    all_rooms = [r for fp in all_floors for r in fp.rooms]

    # ── Stilt / basement habitable room checks ───────────────────────────────
    # Stilt floor: no habitable spaces of any kind
    stilt_banned = {"living", "bedroom", "master_bedroom", "kitchen", "dining",
                    "study", "home_office", "gym", "servant_quarter"}
    # Basement: per NBC — habitable rooms not allowed, but gym/store/utility OK
    basement_banned = {"living", "bedroom", "master_bedroom", "kitchen", "dining",
                       "study", "home_office", "servant_quarter"}

    if getattr(layout.ground_floor, "floor_type", "ground") == "stilt":
        for room in layout.ground_floor.rooms:
            if room.type in stilt_banned:
                violations.append(
                    f"Stilt floor violation: {room.name} ({room.type}) is a habitable space. "
                    "Stilt floors allow only parking, lift lobby, and services."
                )
    if layout.basement_floor is not None:
        for room in layout.basement_floor.rooms:
            if room.type in basement_banned:
                violations.append(
                    f"Basement violation: {room.name} ({room.type}) is not permitted in basement per NBC. "
                    "Allowed: parking, store_room, utility, gym, home_office (with ventilation)."
                )
    if layout.second_floor is not None:
        warnings.append("G+2 building: structural engineer review required (NBC §6).")

    # --- Minimum/maximum room areas ---
    min_bed     = rules["min_bedroom_sqm"]
    min_bed_w   = rules["min_bedroom_width_m"]
    min_kit     = rules["min_kitchen_sqm"]
    min_kit_w   = rules["min_kitchen_width_m"]
    max_kit     = rules.get("max_kitchen_sqm", 15.0)
    min_wc      = rules["min_toilet_sqm"]
    min_wc_w    = rules["min_toilet_width_m"]
    max_wc      = rules.get("max_toilet_sqm", 6.0)
    min_wc_only = rules.get("min_wc_only_sqm", 1.1)
    max_wc_only = rules.get("max_wc_only_sqm", 2.5)
    min_wc_only_w = rules.get("min_wc_only_width_m", 0.9)
    min_bath_m  = rules.get("min_bathroom_master_sqm", 4.5)
    max_bath_m  = rules.get("max_bathroom_master_sqm", 9.0)
    min_bath_m_w = rules.get("min_bathroom_master_width_m", 1.8)
    max_pooja   = rules.get("max_pooja_sqm", 4.5)
    min_pooja_w = rules.get("min_pooja_width_m", 0.9)
    min_p4w     = rules.get("min_parking_4w_sqm", 12.5)
    min_p4w_w   = rules.get("min_parking_4w_width_m", 2.5)
    max_p4w     = rules.get("max_parking_4w_sqm", 30.0)
    min_p2w     = rules.get("min_parking_2w_sqm", 3.0)
    min_p2w_w   = rules.get("min_parking_2w_width_m", 1.2)
    max_p2w     = rules.get("max_parking_2w_sqm", 9.0)
    min_stair_w = rules["min_stair_width_mm"] / 1000

    min_living     = rules.get("min_living_sqm", 9.5)
    min_living_w   = rules.get("min_living_width_m", 2.4)
    min_win_ratio  = rules.get("min_window_to_floor_ratio", 0.1)
    min_bath_vent  = rules.get("min_bath_ventilation_sqm", 0.37)
    min_kit_win    = rules.get("min_kitchen_window_sqm", 1.0)

    # Collect master_bedroom and toilet room sets for adjacency check
    master_beds = [r for r in all_rooms if r.type == "master_bedroom"]
    bath_types  = {"toilet", "wc_only", "bathroom_master"}
    bath_rooms  = [r for r in all_rooms if r.type in bath_types]

    for room in all_rooms:
        if room.type in ("bedroom", "master_bedroom"):
            min_b = rules.get("min_master_bedroom_sqm", 12.0) if room.type == "master_bedroom" else min_bed
            min_bw = rules.get("min_master_bedroom_width_m", 3.0) if room.type == "master_bedroom" else min_bed_w
            if room.area < min_b:
                violations.append(
                    f"{room.name}: {room.area:.1f} sqm < {min_b} sqm minimum (NBC)"
                )
            if min(room.width, room.depth) < min_bw:
                warnings.append(
                    f"{room.name}: width {min(room.width, room.depth):.2f} m "
                    f"< {min_bw} m recommended (NBC 2.4 m habitable)"
                )
            # Ventilation — 1/10th floor area
            req_win = round(room.area * min_win_ratio, 2)
            warnings.append(
                f"{room.name}: provide ≥ {req_win} sqm window opening for ventilation (NBC 1/10th rule)"
            )

        if room.type == "living":
            if room.area < min_living:
                warnings.append(
                    f"{room.name}: {room.area:.1f} sqm < {min_living} sqm recommended (NBC habitable room)"
                )
            if min(room.width, room.depth) < min_living_w:
                warnings.append(
                    f"{room.name}: minimum dimension {min(room.width, room.depth):.2f} m "
                    f"< {min_living_w} m recommended"
                )
            req_win = round(room.area * min_win_ratio, 2)
            warnings.append(
                f"{room.name}: provide ≥ {req_win} sqm window opening for ventilation (NBC 1/10th rule)"
            )

        if room.type == "kitchen":
            if room.area < min_kit:
                violations.append(
                    f"{room.name}: {room.area:.1f} sqm < {min_kit} sqm minimum (NBC)"
                )
            if room.area > max_kit:
                warnings.append(
                    f"{room.name}: {room.area:.1f} sqm > {max_kit} sqm — unusually large for a residential kitchen"
                )
            if min(room.width, room.depth) < min_kit_w:
                warnings.append(
                    f"{room.name}: width {min(room.width, room.depth):.2f} m "
                    f"< {min_kit_w} m recommended (NBC)"
                )
            warnings.append(
                f"{room.name}: provide ≥ {min_kit_win} sqm direct external window opening (NBC kitchen ventilation)"
            )

        if room.type == "toilet":
            if room.area < min_wc:
                violations.append(
                    f"{room.name}: {room.area:.1f} sqm < {min_wc} sqm minimum (NBC)"
                )
            if room.area > max_wc:
                warnings.append(
                    f"{room.name}: {room.area:.1f} sqm > {max_wc} sqm — consider using bathroom_master type for large bathrooms"
                )
            if min(room.width, room.depth) < min_wc_w:
                warnings.append(
                    f"{room.name}: width {min(room.width, room.depth):.2f} m "
                    f"< {min_wc_w} m recommended (NBC)"
                )
            warnings.append(
                f"{room.name}: provide ≥ {min_bath_vent} sqm ventilation opening (NBC bath ventilation)"
            )

        if room.type == "wc_only":
            if room.area < min_wc_only:
                violations.append(
                    f"{room.name}: {room.area:.1f} sqm < {min_wc_only} sqm minimum for WC-only"
                )
            if room.area > max_wc_only:
                warnings.append(
                    f"{room.name}: {room.area:.1f} sqm > {max_wc_only} sqm — too large for a WC-only; use 'toilet' type"
                )
            if min(room.width, room.depth) < min_wc_only_w:
                violations.append(
                    f"{room.name}: width {min(room.width, room.depth):.2f} m < {min_wc_only_w} m minimum"
                )
            warnings.append(
                f"{room.name}: provide ≥ {min_bath_vent} sqm ventilation opening (NBC)"
            )

        if room.type == "bathroom_master":
            if room.area < min_bath_m:
                violations.append(
                    f"{room.name}: {room.area:.1f} sqm < {min_bath_m} sqm minimum for master bathroom"
                )
            if room.area > max_bath_m:
                warnings.append(
                    f"{room.name}: {room.area:.1f} sqm > {max_bath_m} sqm — unusually large"
                )
            if min(room.width, room.depth) < min_bath_m_w:
                warnings.append(
                    f"{room.name}: width {min(room.width, room.depth):.2f} m < {min_bath_m_w} m recommended"
                )
            warnings.append(
                f"{room.name}: provide ≥ {min_bath_vent} sqm ventilation opening (NBC)"
            )

        if room.type == "pooja":
            if min(room.width, room.depth) < min_pooja_w:
                warnings.append(
                    f"{room.name}: width {min(room.width, room.depth):.2f} m < {min_pooja_w} m — too narrow"
                )
            if room.area > max_pooja:
                warnings.append(
                    f"{room.name}: {room.area:.1f} sqm > {max_pooja} sqm — unusually large for a pooja room"
                )

        if room.type == "parking_4w":
            if room.area < min_p4w:
                violations.append(
                    f"{room.name}: {room.area:.1f} sqm < {min_p4w} sqm minimum for car parking (NBC 2.5 m × 5.0 m)"
                )
            if room.area > max_p4w:
                warnings.append(f"{room.name}: {room.area:.1f} sqm > {max_p4w} sqm — unusually large car bay")
            if min(room.width, room.depth) < min_p4w_w:
                violations.append(
                    f"{room.name}: width {min(room.width, room.depth):.2f} m < {min_p4w_w} m minimum (car)"
                )

        if room.type == "parking_2w":
            if room.area < min_p2w:
                violations.append(
                    f"{room.name}: {room.area:.1f} sqm < {min_p2w} sqm minimum for 2-wheeler parking"
                )
            if room.area > max_p2w:
                warnings.append(f"{room.name}: {room.area:.1f} sqm > {max_p2w} sqm — consider splitting into separate bays")
            if min(room.width, room.depth) < min_p2w_w:
                violations.append(
                    f"{room.name}: width {min(room.width, room.depth):.2f} m < {min_p2w_w} m minimum (2-wheeler)"
                )

    # --- Master bedroom attached bathroom check ---
    tol = 0.15  # 15 cm adjacency tolerance
    for mb in master_beds:
        has_attached = False
        for b in bath_rooms:
            # Rooms are adjacent if they share an edge (within tol)
            x_overlap = mb.x < b.x + b.width + tol and b.x < mb.x + mb.width + tol
            y_overlap = mb.y < b.y + b.depth + tol and b.y < mb.y + mb.depth + tol
            x_touch   = (abs(mb.x - (b.x + b.width)) < tol or abs(b.x - (mb.x + mb.width)) < tol)
            y_touch   = (abs(mb.y - (b.y + b.depth)) < tol or abs(b.y - (mb.y + mb.depth)) < tol)
            if (x_touch and y_overlap) or (y_touch and x_overlap):
                has_attached = True
                break
        if not has_attached:
            warnings.append(
                f"{mb.name}: no attached toilet/bathroom detected — Indian practice recommends an en-suite bath"
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
    if cfg.plot_shape == "quadrilateral" and cfg.plot_corners:
        from shapely.geometry import Polygon as _Polygon
        plot_area = _Polygon(cfg.plot_corners).area
    elif cfg.plot_shape == "l_shaped" and cfg.cutout_width > 0 and cfg.cutout_height > 0:
        from app.engine.generator import compute_l_shaped_polygon
        plot_area = compute_l_shaped_polygon(cfg).area
    else:
        plot_area = cfg.plot_width * cfg.plot_length
    coverage_pct = (footprint / plot_area) * 100

    max_cov = rules["max_floor_coverage_pct"]
    if coverage_pct > max_cov:
        violations.append(
            f"Floor coverage {coverage_pct:.1f}% > {max_cov}% maximum — increase setbacks"
        )

    # --- FAR check (city-aware) ---
    # Count habitable floors (basement excluded per most Indian bylaws)
    habitable_floors = sum([
        1,  # GF or stilt
        1,  # FF (always)
        1 if layout.second_floor is not None else 0,
    ])
    total_built = footprint * habitable_floors
    far_limit = get_city_far(cfg.city, cfg.road_width_m, city_data)
    if far_limit is None:
        far_limit = rules.get("default_far", 1.5)
    actual_far = total_built / plot_area
    if actual_far > far_limit + 0.01:
        warnings.append(
            f"FAR {actual_far:.2f} exceeds city limit {far_limit:.2f} for {cfg.city.title()} "
            f"(road width {cfg.road_width_m} m)"
        )

    # --- Room boundary vs. setback lines (above-ground floors only) ---
    ewt = rules["external_wall_thickness_mm"] / 1000
    _l_inset_poly = None
    if cfg.plot_shape == "quadrilateral" and cfg.plot_corners:
        # Derive boundary from the same Shapely inset used by _quad_floor_plate
        from shapely.geometry import Polygon as _Polygon
        _poly = _Polygon(cfg.plot_corners)
        _avg_sb = (cfg.setback_front + cfg.setback_rear + cfg.setback_left + cfg.setback_right) / 4
        _inset = _poly.buffer(-(_avg_sb + ewt), join_style="mitre")
        if _inset.is_empty:
            violations.append("Plot too small after setbacks — no buildable area")
            return ComplianceResult(passed=False, violations=violations, warnings=warnings)
        min_x, min_y, max_x, max_y = _inset.bounds
    elif cfg.plot_shape == "l_shaped" and cfg.cutout_width > 0 and cfg.cutout_height > 0:
        # L-shaped uses the same rectangular setback boundary as the floor plate.
        # The cutout zone is handled by _remove_cutout_overlap in generator.py.
        min_x = cfg.setback_left  + ewt
        max_x = cfg.plot_width    - cfg.setback_right - ewt
        min_y = cfg.setback_front + ewt
        max_y = cfg.plot_length   - cfg.setback_rear  - ewt
    else:
        min_x = cfg.setback_left  + ewt
        max_x = cfg.plot_width    - cfg.setback_right - ewt
        min_y = cfg.setback_front + ewt
        max_y = cfg.plot_length   - cfg.setback_rear  - ewt
    tol   = 0.005  # 5 mm floating-point tolerance
    basement_rooms = set(r.id for r in (layout.basement_floor.rooms if layout.basement_floor else []))
    for room in all_rooms:
        if room.id in basement_rooms:
            continue  # basement has no surface setbacks
        if room.x < min_x - tol or room.x + room.width > max_x + tol:
            violations.append(f"{room.name} extends outside horizontal setback boundary")
        if room.y < min_y - tol or room.y + room.depth > max_y + tol:
            violations.append(f"{room.name} extends outside vertical setback boundary")

    # --- Study/dining ventilation warnings ---
    for room in all_rooms:
        if room.type in ("study", "dining"):
            req_win = round(room.area * min_win_ratio, 2)
            warnings.append(
                f"{room.name}: provide ≥ {req_win} sqm window opening (NBC 1/10th rule)"
            )

    return ComplianceResult(
        passed=len(violations) == 0,
        violations=violations,
        warnings=warnings,
    )
