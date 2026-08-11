"""Reusable harness for reverse-engineering an external reference floor plan
into PlanForge's Room/FloorPlan/PlotConfig schema and rendering it with the
real render_pdf() pipeline -- no solver involved.

Checklist this harness encodes (see docs/superpowers/specs/solver_limitations.md
for why each of these is necessary -- they work around real codebase gaps,
not stylistic preferences):

1. Every adjacent room pair must share an EXACT touching coordinate on the
   shared edge (not "close enough") -- the exterior wall is a Shapely
   union() of room rectangles with no connectivity validation, so a stagger
   silently produces a broken wall, not an error.
2. Road-facing entry rooms must start at `front_y()` (setback + EWT), not
   the raw setback line, or the main door silently fails to place.
3. Parking/car-porch rooms need a real physical gap (`ROOM_GAP`) from every
   neighbouring room -- RoomType "parking_4w"/"parking_2w" are NOT excluded
   from the interior-door pass (only the literal "parking" is, and even
   that's only excluded from *hosting the main door*, not from getting its
   own interior door).
4. Every floor -- including placeholder/unused ones -- needs at least one
   "staircase"-typed room, or section_cut_line() crashes with an uncaught
   StopIteration.

`check_connectivity()` below is a NEW addition (not present in the
production codebase) that catches gap/overlap mistakes BEFORE spending a
render+visual-inspect cycle on them, per the "best-effort single pass, but
catch what you can cheaply" instruction for the bulk reverse-engineering
run.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[5] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.engine.models import ComplianceResult, FloorPlan, Layout, PlotConfig, Room  # noqa: E402
from app.engine.pdf import render_pdf  # noqa: E402

FT = 0.3048
EWT = 0.23  # external wall thickness (app.engine.plan_geometry.EWT)

# NAMING FOOTGUN (see solver_limitations.md limitation F): despite the
# names, PlotConfig.plot_width is the X-extent (road-facing frontage) and
# plot_length is the Y-extent (front-to-rear depth) -- confirmed via
# app/engine/geometry.py:34-35,99 (`W = cfg.plot_width; H = cfg.plot_length;
# box(0, 0, cfg.plot_width, cfg.plot_length)`). This is the OPPOSITE of the
# natural-language reading ("length" = longer/horizontal, "width" =
# shorter) and caused a real, silent bug on the first two Modern-category
# reconstructions: with the fields swapped, render_pdf() does NOT validate
# room coordinates against plot bounds anywhere, so it rendered "clean"
# with no error while buildable_polygon()'s setback box was computed on
# the wrong axis. Always set plot_width=<road-facing frontage in metres>,
# plot_length=<front-to-rear depth in metres>.
ROOM_GAP = 0.15  # metres -- minimum real gap to keep an outdoor room (car
# porch, open terrace) from being treated as "touching" any interior room

# COORDINATE-SNAPPING RECIPE (found during the Modern-category bulk redo,
# 2026-08-10, sharpened to the dyadic form 2026-08-11 -- see
# solver_limitations.md, "Reconstruction workarounds" item 6, for the full
# three-generation failure history): do NOT build a room's x/width (or
# y/depth) as two independently rounded numbers -- round(x1)+round(x2-x1) can
# differ from round(x2) by up to 1e-4 m, and even rounding BOTH corners first
# and then differencing is not fully safe: non-dyadic decimals aren't exact
# binary fractions, so `x + width` (recomputed downstream by
# check_connectivity() / Shapely) can land ~1 ULP from the neighbouring
# room's stored `x`, and unary_union() reports a false DISCONNECTED that is
# indistinguishable from an actual misread adjacency. Snap BOTH corners to a
# DYADIC grid (a power-of-two denominator -- multiples of 2**-10 are exactly
# representable in float64) BEFORE differencing, so adjacency shared-edge
# equality is bit-exact: `x + width == next_room.x` holds bit-for-bit, not
# just "close enough". Use snap_room() below for every room built from
# feet-space source corners.


def ft(feet: float, inches: float = 0.0) -> float:
    """Feet+inches -> metres, PlanForge's native unit."""
    return round((feet + inches / 12.0) * FT, 3)


def front_y(setback_front_m: float) -> float:
    """Y-coordinate a road-facing room's front edge must sit at for
    _place_main_entrance() to find it as a candidate (checklist item 2)."""
    return round(setback_front_m + EWT, 3)


# Dyadic snap grid for room coordinates (see the recipe block in the module
# docstring): multiples of 2**-10 m (~0.98 mm, sub-millimetre for plan
# reconstruction) are exactly representable in float64. Rounding corners to
# 4 decimal places does NOT give exact binary fractions, so `x + width` can
# land ~1 ULP from the neighbour's stored `x` and check_connectivity()
# reports a false DISCONNECTED; dyadic-snapped corners make adjacency
# shared-edge equality bit-exact instead.
_DYADIC_Q = 1024.0


def snap_room(
    rid: str,
    name: str,
    rtype: str,
    x1_ft: float,
    y1_ft: float,
    x2_ft: float,
    y2_ft: float,
    x0_m: float = 0.0,
    y0_m: float = 0.0,
) -> Room:
    """Canonical builder for a Room traced as (x1_ft, y1_ft)-(x2_ft, y2_ft)
    corners on a shared feet grid (checklist item 1, solver_limitations.md
    workaround #6): convert both corners to metres, snap EACH to the dyadic
    grid, then derive width/depth by subtracting the *already-snapped*
    corners -- never round origin and extent independently. x0_m/y0_m are
    optional whole-plan nudges in metres applied BEFORE snapping (e.g.
    Modern-01's +0.047 m y-shift to land the car porch on front_y(0.0)).
    """
    ax = round((x0_m + x1_ft * FT) * _DYADIC_Q) / _DYADIC_Q
    bx = round((x0_m + x2_ft * FT) * _DYADIC_Q) / _DYADIC_Q
    ay = round((y0_m + y1_ft * FT) * _DYADIC_Q) / _DYADIC_Q
    by = round((y0_m + y2_ft * FT) * _DYADIC_Q) / _DYADIC_Q
    return Room(rid, name, rtype, x=ax, y=ay, width=bx - ax, depth=by - ay)


def check_connectivity(rooms: list[Room], label: str = "") -> list[str]:
    """Static pre-render check: (a) no two rooms' rectangles overlap in
    area, (b) the union of all rectangles is a single connected polygon
    (ignoring pure corner touches, which are NOT a valid shared wall).
    Returns a list of human-readable problems; empty list = clean.

    This does NOT exist in the production codebase (see module docstring)
    -- it's the harness's own defense against the exact bug class that
    made both proof-of-concept reconstructions fail on their first render.
    """
    from shapely.geometry import box
    from shapely.ops import unary_union

    problems = []
    boxes = [(r.id, box(r.x, r.y, r.x + r.width, r.y + r.depth)) for r in rooms]

    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            id_a, box_a = boxes[i]
            id_b, box_b = boxes[j]
            inter = box_a.intersection(box_b)
            if inter.area > 1e-6:
                problems.append(
                    f"[{label}] OVERLAP: '{id_a}' and '{id_b}' share "
                    f"{inter.area:.3f} m2 of area (rooms must only touch, never overlap)"
                )

    union = unary_union([b for _, b in boxes])
    n_parts = 1 if union.geom_type == "Polygon" else len(union.geoms)
    if n_parts > 1:
        problems.append(
            f"[{label}] DISCONNECTED: room union has {n_parts} separate "
            "components -- some room doesn't share a real edge (nonzero-width "
            "overlap on the other axis) with the rest of the floor"
        )
    return problems


def build_layout(
    layout_id: str,
    name: str,
    gf_rooms: list[Room],
    ff_rooms: list[Room] | None = None,
    sf_rooms: list[Room] | None = None,
) -> Layout:
    """Assemble a Layout, auto-filling a placeholder first floor with just a
    staircase room (checklist item 4) if the source plan is single-storey
    but render_pdf() still needs a first-floor page."""
    ground = FloorPlan(floor=0, floor_type="ground", rooms=gf_rooms, columns=[])
    if ff_rooms is None:
        stair = next((r for r in gf_rooms if r.type == "staircase"), None)
        if stair is None:
            raise ValueError(
                f"{layout_id}: no first-floor rooms given and ground floor has "
                "no staircase to reuse as a placeholder"
            )
        ff_rooms = [stair]
    first = FloorPlan(floor=1, floor_type="first", rooms=ff_rooms, columns=[])

    layout = Layout(
        id=layout_id,
        name=name,
        ground_floor=ground,
        first_floor=first,
        compliance=ComplianceResult(passed=True),
    )
    if sf_rooms is not None:
        layout.second_floor = FloorPlan(floor=2, floor_type="second", rooms=sf_rooms, columns=[])
    return layout


def render_and_save(
    layout: Layout,
    cfg: PlotConfig,
    num_bedrooms: int,
    project_name: str,
    out_dir: Path,
    file_stub: str,
) -> dict:
    """Render via the real render_pdf() pipeline and save PDF + one PNG per
    architectural page (GF/FF[/SF]) to out_dir. Returns a small report dict
    (page count, PNG paths, any warnings) -- does NOT raise on renderer
    warnings (e.g. "no suitable road-facing room"), only on hard errors.
    """
    import fitz

    out_dir.mkdir(parents=True, exist_ok=True)

    pdf_bytes = render_pdf(
        project_name=project_name,
        layout=layout,
        cfg=cfg,
        num_bedrooms=num_bedrooms,
        watermark_preliminary=False,
    )
    pdf_path = out_dir / f"{file_stub}.pdf"
    pdf_path.write_bytes(pdf_bytes)

    doc = fitz.open(str(pdf_path))
    n_pages = len(doc)
    # NOTE (solver_limitations.md #6a): render_pdf() hard-codes its page
    # loops to [ground_floor, first_floor] only -- layout.second_floor is
    # NEVER rendered as its own architectural page, regardless of layout
    # having one. Page index 2 is always "Ground Floor -- Beam/Column
    # Layout" (structural), not a second-floor plan. Only extract gf/ff.
    floor_labels = ["gf", "ff"]
    png_paths = []
    for i, flabel in enumerate(floor_labels):
        pix = doc[i].get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
        png_path = out_dir / f"re_{flabel}_{file_stub}.png"
        pix.save(str(png_path))
        png_paths.append(str(png_path))
    doc.close()

    return {"pdf": str(pdf_path), "pngs": png_paths, "n_pages": n_pages,
             "second_floor_page_missing": layout.second_floor is not None}


# Open-air RoomType strings: rooms that exist as Room objects only so
# render_pdf() can draw their walls -- excluded from the *enclosed-only*
# floor totals in save_design_json() so that total is comparable to the
# site's declared built-up (carpet/enclosed) area (solver_limitations.md
# finding J).
OPEN_AIR_TYPES = frozenset({"parking", "parking_4w", "parking_2w", "balcony", "courtyard", "garage"})

_FLOOR_LABEL_ALIASES = {"gf": "gf", "ground": "gf", "ff": "ff", "first": "ff", "sf": "sf", "second": "sf"}

_AREA_CONVENTION_NOTE = (
    "AREA CONVENTION (solver_limitations.md finding J): "
    "reconstructed_<floor>_area_all_rooms_sqft sums every modeled Room, "
    "including open-air types (parking, parking_4w, parking_2w, balcony, "
    "courtyard, garage) that exist as Rooms only so render_pdf() can draw "
    "their walls; reconstructed_<floor>_area_enclosed_only_sqft excludes "
    "those open-air types to match the site's declared built-up "
    "(carpet/enclosed) area. The legacy ambiguous "
    "reconstructed_<floor>_area_sqft key -- historically one convention or "
    "the other depending on the design's reconstruction script -- is not "
    "emitted by new files; compare only the *_all_rooms_* and "
    "*_enclosed_only_* totals across designs."
)


def save_design_json(
    out_dir: Path,
    file_stub: str,
    data: dict,
    floors: dict[str, list[Room]] | None = None,
) -> Path:
    """Persist the page-scraped metadata (config, plot/build-up dims, room
    areas, source image URLs) for one design as JSON.

    When `floors` ({label: rooms} with label "gf"/"ff"/"sf" or the spelled-out
    "ground"/"first"/"second") is given, ALSO emit the standardized dual area
    totals per floor going forward (solver_limitations.md finding J):
    `reconstructed_<floor>_area_all_rooms_sqft` (every modeled room) and
    `reconstructed_<floor>_area_enclosed_only_sqft` (OPEN_AIR_TYPES excluded),
    plus a `notes` line documenting this convention. The historically
    ambiguous legacy key `reconstructed_<floor>_area_sqft` is left untouched
    if the caller already put one in `data`, but is not generated here --
    existing re_data_*.json files are dated historical records whose per-file
    `notes` state which convention that key followed.
    """
    if floors:
        for label in ("gf", "ff", "sf"):
            rooms = next(
                (v for k, v in floors.items() if _FLOOR_LABEL_ALIASES.get(k) == label), None
            )
            if rooms is None:
                continue
            all_m2 = sum(r.width * r.depth for r in rooms)
            enclosed_m2 = sum(r.width * r.depth for r in rooms if r.type not in OPEN_AIR_TYPES)
            data[f"reconstructed_{label}_area_all_rooms_sqft"] = round(all_m2 / (FT * FT), 1)
            data[f"reconstructed_{label}_area_enclosed_only_sqft"] = round(
                enclosed_m2 / (FT * FT), 1
            )
        notes = data.get("notes")
        if notes is None:
            data["notes"] = [_AREA_CONVENTION_NOTE]
        elif isinstance(notes, list):
            notes.append(_AREA_CONVENTION_NOTE)
        else:
            data["notes"] = [notes, _AREA_CONVENTION_NOTE]

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{file_stub}.json"
    path.write_text(json.dumps(data, indent=2))
    return path
