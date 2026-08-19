"""CCQS — CAD Quality Composite Score, deterministic components only (0-80).

Extracted from experiments/eval.py. The 5th component (vision-judged visual
quality) intentionally stays a dev-time tool — the CI gate and the user-facing
badge use ONLY these 4 deterministic, API-free components (locked decision,
docs/plans/2026-07-03-fable-stage1-phase0-plan.md).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import fitz  # pymupdf

if TYPE_CHECKING:
    from app.engine.cad_elements import (
        DimChain,
        LabelBox,
        Opening,
        WallJunction,
        WallSegment,
    )
    from app.engine.models import FloorPlan, PlotConfig

_DIM_PATTERN = re.compile(r"\d+'-?\d+\"|\d+\.\d+\s*m")
_FTIN_PATTERN = re.compile(r"\d+'-\d+\"")

DETERMINISTIC_MAX = 80


@dataclass
class CcqsResult:
    total: float
    monochrome: float
    dimension_density: float
    ft_in_labels: float
    layout_completeness: float
    debug: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "max": DETERMINISTIC_MAX,
            "monochrome": self.monochrome,
            "dimension_density": self.dimension_density,
            "ft_in_labels": self.ft_in_labels,
            "layout_completeness": self.layout_completeness,
        }


def _open(pdf_bytes: bytes) -> fitz.Document:
    return fitz.open(stream=pdf_bytes, filetype="pdf")


def compute_monochromaticity(pdf_bytes: bytes) -> float:
    """Render page 0, mean pixel saturation -> 0-20 (low saturation = good)."""
    doc = _open(pdf_bytes)
    try:
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(1.0, 1.0), colorspace=fitz.csRGB)
    finally:
        doc.close()
    samples = pix.samples
    n_pixels = len(samples) // 3
    if n_pixels == 0:
        return 0.0
    total_sat = 0.0
    for i in range(n_pixels):
        r = samples[i * 3] / 255.0
        g = samples[i * 3 + 1] / 255.0
        b = samples[i * 3 + 2] / 255.0
        mx = max(r, g, b)
        total_sat += (mx - min(r, g, b)) / mx if mx > 0 else 0.0
    mean_sat = total_sat / n_pixels
    return round(20 * (1.0 - min(mean_sat, 1.0)), 2)


def compute_text_scores(pdf_bytes: bytes) -> tuple[float, float, float, dict]:
    """Extract all text -> (dim_density, ft_in, completeness, debug)."""
    doc = _open(pdf_bytes)
    try:
        all_text = "".join(pg.get_text() for pg in doc)
    finally:
        doc.close()

    dim_count = len(_DIM_PATTERN.findall(all_text))
    ftin_count = len(_FTIN_PATTERN.findall(all_text))
    dim_score = min(20.0, round(dim_count * 2.0, 2))
    ftin_score = min(20.0, round(ftin_count * 4.0, 2))

    text_upper = all_text.upper()
    both_floors = ("GROUND FLOOR" in text_upper or "G.F" in text_upper) and (
        "FIRST FLOOR" in text_upper or "F.F" in text_upper or "FF" in text_upper
    )
    has_sqft = "SQFT" in text_upper or "SQ.FT" in text_upper or "SQ FT" in text_upper
    has_schedule = (
        "SCHEDULE" in text_upper
        or "STATEMENT" in text_upper
        or ("ROOM" in text_upper and "AREA" in text_upper)
    )
    has_totals = "TOTAL" in text_upper and (
        "AREA" in text_upper or "SQFT" in text_upper or "SQ.FT" in text_upper
    )
    has_compass = "NORTH" in text_upper or " N " in all_text

    completeness = float(
        (4 if both_floors else 0)
        + (4 if has_sqft else 0)
        + (4 if has_schedule else 0)
        + (4 if has_totals else 0)
        + (4 if has_compass else 0)
    )

    debug = {
        "dim_count": dim_count,
        "ftin_count": ftin_count,
        "both_floors": both_floors,
        "has_sqft": has_sqft,
        "has_schedule": has_schedule,
        "has_totals": has_totals,
        "has_compass": has_compass,
    }
    return dim_score, ftin_score, completeness, debug


def compute_ccqs_deterministic(pdf_bytes: bytes) -> CcqsResult:
    mono = compute_monochromaticity(pdf_bytes)
    dim_score, ftin_score, completeness, debug = compute_text_scores(pdf_bytes)
    total = round(mono + dim_score + ftin_score + completeness, 2)
    return CcqsResult(
        total=total,
        monochrome=mono,
        dimension_density=dim_score,
        ft_in_labels=ftin_score,
        layout_completeness=completeness,
        debug=debug,
    )


# ── Geometric Correctness Score (Sprint 7) ──────────────────────────────────
# Computed directly from the canonical FloorDrawing (app.engine.plan_geometry.
# build_floor_drawing), not from rendered pixels/text. Replaces CCQS as the
# export quality gate: CCQS's 80 deterministic points are gameable regex/pixel
# checkboxes maxed out early, and the remaining 20 (a stochastic vision-judge
# call) plateaued near 16/20 regardless of real drawing-quality changes — see
# docs/superpowers/plans/2026-07-05-combined-phase3-cad-quality.md. CCQS is
# kept as-is (still used by GET /layouts/{id}/quality) pending a separate
# decision on full deprecation.

GCS_MAX = 100
_GCS_HABITABLE = {
    "living",
    "bedroom",
    "master_bedroom",
    "kitchen",
    "study",
    "dining",
    "home_office",
    "gym",
    "servant_quarter",
}


@dataclass
class GcsResult:
    total: float
    phantom_walls: int
    collisions: int
    label_overflow: int
    dimension_coverage_pct: float
    standard_scale: bool
    doors_per_room_ok: bool
    windows_per_habitable_ok: bool
    opening_clearance_violations: int
    debug: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "max": GCS_MAX,
            "phantom_walls": self.phantom_walls,
            "collisions": self.collisions,
            "label_overflow": self.label_overflow,
            "dimension_coverage_pct": self.dimension_coverage_pct,
            "standard_scale": self.standard_scale,
            "doors_per_room_ok": self.doors_per_room_ok,
            "windows_per_habitable_ok": self.windows_per_habitable_ok,
            "opening_clearance_violations": self.opening_clearance_violations,
        }


def _phantom_wall_count(rooms: list, walls: list[WallSegment]) -> int:
    """A wall that bisects a room's interior instead of living in the
    inter-room gap/exterior ring (the plan_geometry.py room-layout
    convention) would be a phantom wall — should never happen once every
    renderer consumes the same canonical derivation, so this is a
    regression check, not a routine occurrence."""
    from shapely.geometry import box

    from app.engine.plan_geometry import wall_polygons

    polys = wall_polygons(walls)
    count = 0
    for room in rooms:
        room_box = box(room.x, room.y, room.x + room.width, room.y + room.depth).buffer(
            -0.02
        )
        if room_box.is_empty:
            continue
        for kind in ("external", "internal"):
            geom = polys[kind]
            if not geom.is_empty and geom.intersection(room_box).area > 0.01:
                count += 1
                break
    return count


def _collision_count(openings: list[Opening], columns: list) -> int:
    from shapely.geometry import box

    from app.engine.plan_geometry import opening_boxes

    boxes = opening_boxes(openings)
    count = 0
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if boxes[i].intersection(boxes[j]).area > 1e-4:
                count += 1
    col_boxes = [
        box(c.cx - c.size / 2, c.cy - c.size / 2, c.cx + c.size / 2, c.cy + c.size / 2)
        for c in columns
    ]
    for ob in boxes:
        for cb in col_boxes:
            if ob.intersection(cb).area > 1e-4:
                count += 1
    return count


def _label_overflow_count(labels: list[LabelBox], rooms_by_id: dict) -> int:
    """Re-checks derive_labels' own fit decision (same margin/measurement
    convention) — a label without a leader is only ever emitted when some
    (lines, font) combination already passed this exact test, so a non-zero
    count here means that invariant broke."""
    from app.engine.plan_geometry import _LABEL_MARGIN, _PT_TO_MODEL_M, _text_width_m

    count = 0
    for lb in labels:
        if lb.leader is not None:
            continue
        room = rooms_by_id.get(lb.room_id)
        if room is None:
            continue
        avail_w = (room.depth if lb.rotated else room.width) - _LABEL_MARGIN
        avail_h = (room.width if lb.rotated else room.depth) - _LABEL_MARGIN
        max_line_w = max(_text_width_m(t, lb.font_pt) for t in lb.lines)
        total_h = len(lb.lines) * lb.font_pt * 1.3 * _PT_TO_MODEL_M
        if max_line_w > avail_w or total_h > avail_h:
            count += 1
    return count


def _dimension_coverage_pct(dim_chains: list[DimChain]) -> float:
    """% of room-level (level 0) dimension chains whose entries tile their
    span with no gaps — a gap means some wall run went undimensioned."""
    level0 = [c for c in dim_chains if c.level == 0 and c.entries]
    if not level0:
        return 0.0
    gap_free = sum(
        1
        for chain in level0
        if all(
            abs(b.start - a.end) <= 0.02
            for a, b in zip(chain.entries, chain.entries[1:])
        )
    )
    return round(100.0 * gap_free / len(level0), 1)


def _doors_per_room_ok(rooms: list, openings: list[Opening]) -> bool:
    """Every non-passage room has a door on one of its boundary walls.

    Checked by spatial proximity, not swing_into_room_id: a door between two
    rooms swings into only ONE of them (priority order in plan_geometry.py's
    _DOOR_NEIGHBOUR_PRIORITY), but it still serves both rooms' access.
    """
    doors = [op for op in openings if op.kind == "door"]
    for room in rooms:
        if room.type == "passage":
            continue
        on_boundary = any(
            room.x - 0.3 <= op.cx <= room.x + room.width + 0.3
            and room.y - 0.3 <= op.cy <= room.y + room.depth + 0.3
            for op in doors
        )
        if not on_boundary:
            return False
    return True


def _windows_per_habitable_ok(rooms: list, openings: list[Opening]) -> bool:
    windows = [op for op in openings if op.kind == "window"]
    for room in rooms:
        if room.type not in _GCS_HABITABLE:
            continue
        found = any(
            room.x - 0.3 <= op.cx <= room.x + room.width + 0.3
            and room.y - 0.3 <= op.cy <= room.y + room.depth + 0.3
            for op in windows
        )
        if not found:
            return False
    return True


# ── Opening positional buildability (Task 9E) ───────────────────────────────
# GCS scored openings for presence, collision and containment only — nothing
# said whether an opening sits somewhere a mason could actually build it. An
# opening butted hard against a wall end or separated from its neighbour by a
# 30 mm slice of masonry passes every other check in this module.
#
# Threshold basis, stated honestly: NBC 2016 and the IS masonry codes give
# minimum opening SIZES (main door >= 1000 mm, habitable-room door 900 mm,
# etc.) but no minimum jamb return or inter-opening pier dimension that could
# be cited here. So this is an explicit convention, not a code quotation:
# 115 mm — one half-brick, the standard Indian masonry leaf, and enough to
# take the ~50-75 mm per-side frame allowance a 900 mm leaf needs. It is also
# already this repo's own placement constraint (`plan_geometry._JAMB`), which
# makes the check a re-verification of the derivation's stated invariant
# rather than a new opinion imposed on it — the same relationship
# `_label_overflow_count` above has to `derive_labels`.
_OPENING_POS_EPS = 1e-4  # 0.1 mm — float noise, not real slack
_WALL_COORD_EPS = 0.05  # an opening centre sits ON its wall's centreline


def _wall_runs(walls: list[WallSegment]) -> list[tuple[bool, float, float, float]]:
    """Merge axis-aligned wall centrelines into continuous masonry runs.

    Openings are placed against a wall RUN, not against the individual
    segments a FloorDrawing carries, so the clearance check has to rebuild
    the same notion: collinear segments that touch or overlap are one run.
    Sloped walls (the trapezoid plot's sides) are skipped — an `Opening` is
    always axis-aligned, so it never hosts one.

    Divergence risk, stated so the next reader is not surprised: this is a
    RECONSTRUCTION of a notion that `plan_geometry` owns (it derives per-room
    wall spans directly, via `_ObstacleIndex` and the adjacency spans the
    placement loop clamps against). The two can drift apart silently — if
    `plan_geometry` changes how a run is bounded, this stays on the old
    model and the metric quietly measures the wrong thing. Hoisting a shared
    helper into `plan_geometry` (and promoting `_JAMB` to public) would fix
    that properly; it was left alone deliberately because it is a
    cross-module refactor of the derivation, out of scope for a scorer.
    The direction of failure is benign — a merged run is never SHORTER than
    the real span, so a mismatch under-reports rather than false-positives.

    Returns (is_horizontal, cross-axis coord, along-axis lo, along-axis hi).
    """
    buckets: dict[tuple[bool, float], list[list[float]]] = {}
    for w in walls:
        horizontal = abs(w.y1 - w.y2) <= _OPENING_POS_EPS
        vertical = abs(w.x1 - w.x2) <= _OPENING_POS_EPS
        if horizontal == vertical:  # diagonal, or a zero-length stub
            continue
        coord = (w.y1 + w.y2) / 2 if horizontal else (w.x1 + w.x2) / 2
        span = sorted((w.x1, w.x2) if horizontal else (w.y1, w.y2))
        buckets.setdefault((horizontal, round(coord, 3)), []).append(span)

    runs: list[tuple[bool, float, float, float]] = []
    for (horizontal, coord), spans in sorted(buckets.items()):
        spans.sort()
        cur_lo, cur_hi = spans[0]
        for lo, hi in spans[1:]:
            if lo <= cur_hi + _OPENING_POS_EPS:
                cur_hi = max(cur_hi, hi)
            else:
                runs.append((horizontal, coord, cur_lo, cur_hi))
                cur_lo, cur_hi = lo, hi
        runs.append((horizontal, coord, cur_lo, cur_hi))
    return runs


def _opening_clearance_violations(
    openings: list[Opening],
    walls: list[WallSegment],
    junctions: list[WallJunction],
) -> tuple[int, list[str]]:
    """Count openings placed somewhere unbuildable.

    Three defects, all of which leave a mason with masonry that cannot be
    laid, and all measured against the same 115 mm minimum:

    1. **Jamb clearance** — masonry between the opening's edge and the
       nearest hard boundary on its own wall: the run's end, or a wall
       junction (a perpendicular wall landing on the run) between them.
    2. **Pier width** — masonry between two openings on the same run.
    3. **Containment** — the opening lies within a wall run at all, and no
       junction falls inside its span.

    Known limit: junctions come from the drawing's own derivation, so a
    perpendicular wall that failed to produce a junction is invisible here.
    Returns (count of distinct offending openings, human-readable reasons).
    """
    from app.engine.plan_geometry import _JAMB

    runs = _wall_runs(walls)
    jamb_min = _JAMB - _OPENING_POS_EPS
    faults: dict[int, list[str]] = {}
    on_run: dict[int, list[tuple[float, float, int]]] = {}
    where_by_idx: dict[int, str] = {}

    for idx, op in enumerate(openings):
        along = op.cx if op.is_horizontal else op.cy
        cross = op.cy if op.is_horizontal else op.cx
        lo_edge, hi_edge = along - op.width / 2, along + op.width / 2
        where = f"{op.kind} @({op.cx:.3f},{op.cy:.3f})"
        where_by_idx[idx] = where

        host = next(
            (
                (r_idx, r_lo, r_hi)
                for r_idx, (horizontal, coord, r_lo, r_hi) in enumerate(runs)
                if horizontal == op.is_horizontal
                and abs(coord - cross) <= _WALL_COORD_EPS
                and r_lo - _OPENING_POS_EPS <= along <= r_hi + _OPENING_POS_EPS
            ),
            None,
        )
        if host is None:
            faults.setdefault(idx, []).append(f"{where} lies on no wall run")
            continue
        r_idx, r_lo, r_hi = host

        # Junctions where a perpendicular wall lands on this run. Kept apart
        # from the run's own ends so the two failure modes below can be told
        # apart: an opening running off the END of the wall and an opening
        # straddling a junction MID-run are different defects, and the
        # message is what the baseline test prints on failure.
        junction_positions = [
            j_along
            for j in junctions
            for j_along, j_cross in [(j.x, j.y) if op.is_horizontal else (j.y, j.x)]
            if abs(j_cross - cross) <= _WALL_COORD_EPS
            and r_lo - _OPENING_POS_EPS <= j_along <= r_hi + _OPENING_POS_EPS
        ]

        straddled = [
            b
            for b in junction_positions
            if lo_edge + _OPENING_POS_EPS < b < hi_edge - _OPENING_POS_EPS
        ]
        if lo_edge < r_lo - _OPENING_POS_EPS or hi_edge > r_hi + _OPENING_POS_EPS:
            faults.setdefault(idx, []).append(
                f"{where} extends past its wall run "
                f"({lo_edge:.3f}..{hi_edge:.3f} outruns {r_lo:.3f}..{r_hi:.3f})"
            )
        elif straddled:
            faults.setdefault(idx, []).append(
                f"{where} spans a wall junction at {straddled[0]:.3f}"
            )
        else:
            bounds = [r_lo, r_hi, *junction_positions]
            left = max(
                (b for b in bounds if b <= lo_edge + _OPENING_POS_EPS), default=r_lo
            )
            right = min(
                (b for b in bounds if b >= hi_edge - _OPENING_POS_EPS), default=r_hi
            )
            clearance = min(lo_edge - left, right - hi_edge)
            if clearance < jamb_min:
                faults.setdefault(idx, []).append(
                    f"{where} jamb clearance {clearance:.3f}m < {_JAMB}m"
                )

        on_run.setdefault(r_idx, []).append((lo_edge, hi_edge, idx))

    for entries in on_run.values():
        entries.sort()
        for (_, a_hi, a_idx), (b_lo, _, b_idx) in zip(entries, entries[1:]):
            pier = b_lo - a_hi
            if pier < jamb_min:
                for i, other in ((a_idx, b_idx), (b_idx, a_idx)):
                    faults.setdefault(i, []).append(
                        f"{where_by_idx[i]} pier {pier:.3f}m to "
                        f"{where_by_idx[other]} < {_JAMB}m"
                    )

    return len(faults), [msg for _, msgs in sorted(faults.items()) for msg in msgs]


def compute_gcs(floorplan: FloorPlan, cfg: PlotConfig) -> GcsResult:
    """Deterministic Geometric Correctness Score — the export quality gate."""
    from reportlab.lib.pagesizes import A4

    from app.engine.pdf import _standard_scale
    from app.engine.plan_geometry import build_floor_drawing

    drawing = build_floor_drawing(floorplan, cfg)
    rooms_by_id = {r.id: r for r in floorplan.rooms}

    phantom = _phantom_wall_count(floorplan.rooms, drawing.walls)
    collisions = _collision_count(drawing.openings, drawing.columns)
    overflow = _label_overflow_count(drawing.labels, rooms_by_id)
    coverage = _dimension_coverage_pct(drawing.dim_chains)
    _, denom = _standard_scale(cfg, *A4)
    standard = denom in (50, 100, 200)
    doors_ok = _doors_per_room_ok(floorplan.rooms, drawing.openings)
    windows_ok = _windows_per_habitable_ok(floorplan.rooms, drawing.openings)
    clearance_bad, clearance_reasons = _opening_clearance_violations(
        drawing.openings, drawing.walls, drawing.junctions
    )

    # GCS_MAX stays 100 — the 10 points for opening clearance are taken from
    # dimension coverage (20 -> 15) and standard scale (10 -> 5), the two
    # presentation/documentation dimensions. Whether a sheet plots at 1:100
    # and whether every run is dimensioned matter, but neither decides
    # whether the building can be built; an unbuildable opening does.
    total = round(
        (20 if phantom == 0 else 0)
        + (20 if collisions == 0 else 0)
        + (20 if overflow == 0 else 0)
        + coverage / 100 * 15
        + (5 if standard else 0)
        + (5 if doors_ok else 0)
        + (5 if windows_ok else 0)
        + (10 if clearance_bad == 0 else 0),
        1,
    )
    return GcsResult(
        total=total,
        phantom_walls=phantom,
        collisions=collisions,
        label_overflow=overflow,
        dimension_coverage_pct=coverage,
        standard_scale=standard,
        doors_per_room_ok=doors_ok,
        windows_per_habitable_ok=windows_ok,
        opening_clearance_violations=clearance_bad,
        debug={"opening_clearance": clearance_reasons},
    )
