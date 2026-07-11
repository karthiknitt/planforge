# Sectional Elevation (Section A-A) + Front Elevation Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task (per Karthik's standing rule — never the parallel-session option). Steps use checkbox (`- [ ]`) syntax for tracking. **Standing rule [[feedback_finish_and_wait]]: finish one task, commit, STOP and wait for go-ahead.**
>
> **EXECUTION GATE (Karthik, 2026-07-11):** Do NOT begin execution until Karthik gives the explicit go-ahead — primary bugs are being fixed in another session first. Each task carries an **Agent model** assignment (haiku / sonnet / opus by complexity); dispatch each task's implementation subagent on that model. Code review between tasks stays with the main session.

**Goal:** Extend both PDF generators (standard `pdf.py` and approval `approval_pdf.py`) to produce a convention-faithful **SECTION A-A** (cut through the staircase) and a **FRONT ELEVATION** page, built from Shapely geometry, annotated to the same professional standard as the existing plan pages (IS 962 line weights, material hatching, level markers, vertical dimension chains, dual-scale titles).

**Context:** Research (IS 962:1989 + Indian municipal bye-laws, sources archived in "Research reference" below) established that a permit set needs at least one section cut through the staircase plus a front elevation, both at 1:100. Today the approval PDF has only a schematic box-stack section (`_draw_section_view`, `approval_pdf.py:757-930`) — no staircase profile, no openings, no material hatching, no cut-vs-beyond distinction — and no elevation exists anywhere in the backend. Vertical dimensions are hardcoded in 3 places. User decisions (2026-07-10): **both PDFs**, **Section A-A only**, **front elevation only**, **foundation depth 900 mm**.

**Architecture:** Mirror the existing plan pipeline (`plan_geometry.py` → `FloorDrawing` → renderer). A new `section_geometry.py` derives canonical `SectionDrawing` / `ElevationDrawing` dataclasses (pure Shapely, unit-testable, no ReportLab); a new `section_render.py` renders them onto a ReportLab canvas (hatching via clip paths, level markers, vertical dim chains); `pdf.py` and `approval_pdf.py` both compose pages from these shared modules. A new `vertical_standards.py` becomes the single source of truth for all vertical dimensions.

**Tech Stack:** Python 3.12, Shapely (geometry only), ReportLab (rendering only), pytest, uv.

## Sub-agent model assignment (by task complexity)

| Task | Deliverable | Complexity | Agent model |
|---|---|---|---|
| 0 | Branch + plan archival | Trivial mechanical | **haiku** |
| 1 | `vertical_standards.py` + constant re-pointing | Simple, fully specified | **haiku** |
| 2 | Cut-line + cut-interval geometry | Moderate (complete code provided) | **sonnet** |
| 3 | `derive_section()` — SectionDrawing | **Hardest**: 11 construction rules, geometric edge cases | **opus** |
| 4 | `derive_elevation()` — ElevationDrawing | Moderate projection logic | **sonnet** |
| 5 | `section_render.py` — ReportLab hatching/annotations | High: clip-path hatching, visual quality gate | **opus** |
| 6 | Standard PDF wiring + plan markers | Moderate integration (existing transforms) | **sonnet** |
| 7 | Approval PDF wiring + old-section removal | Moderate integration | **sonnet** |
| 8 | CCQS baseline, full suite, docs | Mechanical | **haiku** |

## Global Constraints

- Package manager: `uv` only (`uv run pytest`, `uv add` — never pip)
- Lint/format: `uv run ruff format .` && `uv run ruff check .` must pass before every commit
- Geometry math: Shapely only, never raw float math for polygon ops
- Shapely dispatch: use `.geom_type` string dispatch, NOT `hasattr(poly, "geoms")` (memory: patterns.md)
- PDF: ReportLab only (not matplotlib/cairosvg)
- Type hints mandatory on all functions; no docstrings/comments unless logic is non-obvious
- All new pages must stay strictly monochrome (CCQS monochromaticity; existing tests assert mean saturation < 0.02)
- Conventional commits; work on branch `feat/section-elevation-views`; never merge to main directly
- TDD: every task writes the failing test first
- Section-space coordinate system (used everywhere): `s` = distance in metres along the cut line / facade axis, `z` = elevation in metres relative to GF FFL (±0.00 datum). GL = `-plinth_h_m`.

## Vertical defaults (researched, user-approved)

| Constant | Value | Note |
|---|---|---|
| floor_to_floor_m | 3.0 | matches existing `FLOOR_HEIGHT_M` |
| slab_t_m | 0.15 | |
| plinth_h_m | 0.45 | GL = −0.450 |
| foundation_depth_m | 0.90 | **changed from 0.6** (user approved) |
| footing_w_m | 0.75, footing_t_m 0.30 | PCC pad |
| sill_h_m | 0.90 | window sill above FFL |
| lintel_h_m | 2.10 | door head = window head |
| lintel_t_m | 0.15 | RCC lintel band |
| door_h_m | 2.10 | |
| vent_sill_m | 1.50 | ventilator sill |
| chajja_proj_m | 0.45, chajja_t_m 0.10 | over external openings |
| parapet_h_m | 1.00, parapet_t_m 0.23 | |
| stair_riser_m | 0.175, stair_tread_m 0.25, waist_t_m 0.15 | matches derive_stair |

Materials → hatch (IS 962 Table 7, monochrome): `brick` = 45° single hatch; `rcc` = 45° crosshatch; `pcc` = dot/stipple; `earth` = short irregular 60° dashes. Cut outline 1.4 pt, thin/beyond/dimension 0.5 pt (≥2:1 per IS 962).

---

### Task 0: Branch + plan archival

**Agent model:** haiku

**Files:**
- Commit: `docs/superpowers/plans/2026-07-11-section-elevation-views.md` (this file, already on disk)

- [ ] **Step 1:** `git checkout -b feat/section-elevation-views` (from up-to-date `main`)
- [ ] **Step 2:** `git add docs/superpowers/plans/2026-07-11-section-elevation-views.md && git commit -m "docs: add section/elevation implementation plan"`

---

### Task 1: `vertical_standards.py` — single source of vertical truth

**Agent model:** haiku

**Files:**
- Create: `backend/app/engine/vertical_standards.py`
- Modify: `backend/app/engine/boq.py:12` (FLOOR_HEIGHT_M), `backend/app/engine/approval_pdf.py:766-770` (five hardcoded constants in `_draw_section_view` — only re-pointed here; the function itself is replaced in Task 7)
- Test: `backend/tests/test_vertical_standards.py`

**Interfaces:**
- Produces: `VerticalStandards` frozen dataclass + module-level default instance `VS`; `fmt_level(z: float) -> str` (level-marker text: `±0.00`, `+3.000`, `-0.450`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_vertical_standards.py
from app.engine.vertical_standards import VS, fmt_level


def test_defaults_match_indian_conventions():
    assert VS.floor_to_floor_m == 3.0
    assert VS.slab_t_m == 0.15
    assert VS.plinth_h_m == 0.45
    assert VS.foundation_depth_m == 0.9
    assert VS.sill_h_m == 0.9
    assert VS.lintel_h_m == 2.1
    assert VS.door_h_m == 2.1
    assert VS.parapet_h_m == 1.0
    assert VS.stair_riser_m == 0.175
    assert VS.stair_tread_m == 0.25


def test_fmt_level():
    assert fmt_level(0.0) == "±0.00"
    assert fmt_level(3.0) == "+3.000"
    assert fmt_level(-0.45) == "-0.450"
```

- [ ] **Step 2:** Run `cd backend && uv run pytest tests/test_vertical_standards.py -v` — expect FAIL (ModuleNotFoundError)
- [ ] **Step 3: Implement**

```python
# backend/app/engine/vertical_standards.py
from dataclasses import dataclass


@dataclass(frozen=True)
class VerticalStandards:
    floor_to_floor_m: float = 3.0
    slab_t_m: float = 0.15
    plinth_h_m: float = 0.45
    foundation_depth_m: float = 0.9
    footing_w_m: float = 0.75
    footing_t_m: float = 0.3
    sill_h_m: float = 0.9
    lintel_h_m: float = 2.1
    lintel_t_m: float = 0.15
    door_h_m: float = 2.1
    vent_sill_m: float = 1.5
    chajja_proj_m: float = 0.45
    chajja_t_m: float = 0.1
    parapet_h_m: float = 1.0
    parapet_t_m: float = 0.23
    stair_riser_m: float = 0.175
    stair_tread_m: float = 0.25
    waist_t_m: float = 0.15


VS = VerticalStandards()


def fmt_level(z: float) -> str:
    if abs(z) < 0.005:
        return "±0.00"
    return f"{z:+.3f}"
```

- [ ] **Step 4:** Re-point existing constants (no behavior change except foundation depth 0.6→0.9):
  - `boq.py:12`: `FLOOR_HEIGHT_M = VS.floor_to_floor_m` (import `VS` at top)
  - `approval_pdf.py:766-770`: replace the five local literals with `VS.floor_to_floor_m`, `VS.slab_t_m`, `VS.parapet_h_m`, `VS.foundation_depth_m`, and keep `ewt` reading from compliance config as today
- [ ] **Step 5:** Run `uv run pytest tests/test_vertical_standards.py tests/test_boq_city_rates.py tests/test_approval_site_plan.py -v` — expect PASS
- [ ] **Step 6:** `uv run ruff format . && uv run ruff check .` then commit: `feat(engine): centralize vertical dimension standards (IS-convention defaults)`

---

### Task 2: Section cut line + cut intervals (`section_geometry.py`, part 1)

**Agent model:** sonnet

**Files:**
- Create: `backend/app/engine/section_geometry.py`
- Test: `backend/tests/test_section_geometry.py`

**Interfaces:**
- Consumes: `Room`, `PlotConfig` from `app.engine.models`; `buildable_polygon(cfg)` from `app.engine.geometry`; `WallSegment` from `app.engine.cad_elements`.
- Produces:
  - `section_cut_line(rooms: list[Room], buildable: Polygon) -> tuple[LineString, bool]` — cut through staircase centreline, along the stair-run direction, extended 1 m past the buildable bounds; returns `(line, along_y)` where `along_y=True` means the line runs parallel to the y-axis.
  - `wall_cut_intervals(line: LineString, wall: WallSegment) -> list[tuple[float, float]]` — sorted `(s0, s1)` chainage intervals where the line crosses that wall's footprint box.
  - `room_interval(line: LineString, room: Room) -> tuple[float, float] | None`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_section_geometry.py
from shapely.geometry import LineString, Point, box

from app.engine.cad_elements import WallSegment
from app.engine.generator import generate
from app.engine.geometry import buildable_polygon
from app.engine.models import PlotConfig
from app.engine.section_geometry import (
    room_interval,
    section_cut_line,
    wall_cut_intervals,
)

CFG = PlotConfig(
    plot_length=12.0, plot_width=9.0,
    setback_front=3.0, setback_rear=1.5, setback_left=1.0, setback_right=1.0,
    num_bedrooms=2, toilets=2, parking=True,
)


def _layout():
    return generate(CFG)[0]


def test_cut_line_passes_through_staircase():
    lay = _layout()
    stair = next(r for r in lay.ground_floor.rooms if r.type == "staircase")
    line, along_y = section_cut_line(lay.ground_floor.rooms, buildable_polygon(CFG))
    stair_box = box(stair.x, stair.y, stair.x + stair.width, stair.y + stair.depth)
    assert line.intersects(stair_box)
    assert along_y == (stair.depth >= stair.width)


def test_cut_line_spans_full_building():
    lay = _layout()
    bp = buildable_polygon(CFG)
    line, _ = section_cut_line(lay.ground_floor.rooms, bp)
    assert line.length >= max(bp.bounds[2] - bp.bounds[0], bp.bounds[3] - bp.bounds[1])


def test_wall_cut_interval_width_matches_thickness():
    line = LineString([(5.0, -1.0), (5.0, 11.0)])
    wall = WallSegment(x1=2.0, y1=4.0, x2=8.0, y2=4.0, thickness=0.23, kind="external")
    ivs = wall_cut_intervals(line, wall)
    assert len(ivs) == 1
    s0, s1 = ivs[0]
    assert abs((s1 - s0) - 0.23) < 0.01


def test_parallel_wall_not_cut():
    line = LineString([(5.0, -1.0), (5.0, 11.0)])
    wall = WallSegment(x1=2.0, y1=4.0, x2=2.0, y2=9.0, thickness=0.115, kind="internal")
    assert wall_cut_intervals(line, wall) == []


def test_room_interval():
    line = LineString([(5.0, -1.0), (5.0, 11.0)])
    from app.engine.models import Room
    r = Room(id="r1", name="Living", type="living", x=3.0, y=2.0, width=4.0, depth=5.0)
    iv = room_interval(line, r)
    assert iv is not None
    assert abs((iv[1] - iv[0]) - 5.0) < 0.01
```

Note for implementer: check `Room`'s actual constructor (`app/engine/models.py:33-44`) — `type` is a `RoomType`; if it is an Enum, construct with `RoomType("living")` / compare with `r.type == RoomType.STAIRCASE` and adjust the two tests accordingly. `models.py:14` shows `"staircase"` as the string value.

- [ ] **Step 2:** Run `uv run pytest tests/test_section_geometry.py -v` — expect FAIL (import error)
- [ ] **Step 3: Implement**

```python
# backend/app/engine/section_geometry.py
from shapely.geometry import LineString, Point, Polygon, box

from app.engine.cad_elements import WallSegment
from app.engine.models import Room


def _line_segments(geom) -> list[LineString]:
    if geom.is_empty:
        return []
    if geom.geom_type == "LineString":
        return [geom]
    if geom.geom_type in ("MultiLineString", "GeometryCollection"):
        return [g for g in geom.geoms if g.geom_type == "LineString"]
    return []


def section_cut_line(rooms: list[Room], buildable: Polygon) -> tuple[LineString, bool]:
    stair = next(r for r in rooms if getattr(r.type, "value", r.type) == "staircase")
    minx, miny, maxx, maxy = buildable.bounds
    along_y = stair.depth >= stair.width
    if along_y:
        cx = stair.x + stair.width / 2
        return LineString([(cx, miny - 1.0), (cx, maxy + 1.0)]), True
    cy = stair.y + stair.depth / 2
    return LineString([(minx - 1.0, cy), (maxx + 1.0, cy)]), False


def _intervals(line: LineString, poly: Polygon) -> list[tuple[float, float]]:
    out = []
    for seg in _line_segments(line.intersection(poly)):
        t0 = line.project(Point(seg.coords[0]))
        t1 = line.project(Point(seg.coords[-1]))
        if abs(t1 - t0) > 1e-6:
            out.append((min(t0, t1), max(t0, t1)))
    return sorted(out)


def wall_cut_intervals(line: LineString, wall: WallSegment) -> list[tuple[float, float]]:
    h = wall.thickness / 2
    wall_box = box(min(wall.x1, wall.x2) - h, min(wall.y1, wall.y2) - h,
                   max(wall.x1, wall.x2) + h, max(wall.y1, wall.y2) + h)
    # skip walls the line runs along (parallel & coincident): interval far wider than thickness
    return [iv for iv in _intervals(line, wall_box) if (iv[1] - iv[0]) <= wall.thickness * 2.5]


def room_interval(line: LineString, room: Room) -> tuple[float, float] | None:
    ivs = _intervals(line, box(room.x, room.y, room.x + room.width, room.y + room.depth))
    return ivs[0] if ivs else None
```

Resolve the `RoomType` comparison to the actual enum/string form found in `models.py` — pick the one correct comparison, don't keep a defensive `getattr` if the type is a plain string.

- [ ] **Step 4:** Run `uv run pytest tests/test_section_geometry.py -v` — expect PASS
- [ ] **Step 5:** `ruff format`/`check`, commit: `feat(engine): section cut-line and cut-interval geometry`

---

### Task 3: `SectionDrawing` + `derive_section()` (part 2)

**Agent model:** opus

**Files:**
- Modify: `backend/app/engine/section_geometry.py` (extend)
- Test: `backend/tests/test_section_geometry.py` (extend)

**Interfaces:**
- Consumes: `build_floor_drawing(floorplan, cfg) -> FloorDrawing` (`plan_geometry.py:932`) for walls/openings/stair per floor; Task 1 `VS`, `fmt_level`; Task 2 functions.
- Produces (all in section-space `(s, z)` metres):

```python
@dataclass
class SectionPoly:
    poly: Polygon
    material: str  # "brick" | "rcc" | "pcc" | "earth"
    cut: bool = True

@dataclass
class LevelMark:
    s: float
    z: float
    label: str

@dataclass
class VDim:
    z1: float
    z2: float
    label: str  # e.g. "3000"

@dataclass
class SectionDrawing:
    title: str                                  # "SECTION A-A"
    polys: list[SectionPoly]
    labels: list[tuple[float, float, str]]       # room names (s, z, text)
    levels: list[LevelMark]
    vdims: list[VDim]
    gl_z: float                                  # -0.45
    bounds: tuple[float, float, float, float]    # (s_min, z_min, s_max, z_max)

def derive_section(layout: Layout, cfg: PlotConfig, vs: VerticalStandards = VS) -> SectionDrawing
```

**Construction rules (implement exactly):**
1. Floors = `[layout.ground_floor, layout.first_floor]` + `layout.second_floor` if present. `z_ffl(i) = i * vs.floor_to_floor_m`; `roof_z = n_floors * ftf`.
2. Per floor, per wall, per cut interval `(s0, s1)`: full-height brick strip `box(s0, z_ffl, s1, z_ffl + ftf)`. If an opening sits in that wall AND the cut passes through its span (along_y cut: `wall horizontal` and `|op.cx − line_x| < op.width/2`; along_x cut: symmetric with `cy`/`line_y`), subtract the vertical gap and add extras:
   - door → gap `(z_ffl, z_ffl + vs.door_h_m)`
   - window → gap `(z_ffl + vs.sill_h_m, z_ffl + vs.lintel_h_m)`
   - ventilator → gap `(z_ffl + vs.vent_sill_m, z_ffl + vs.lintel_h_m)`
   - always: RCC lintel band `box(s0, z_ffl + lintel, s1, z_ffl + lintel + lintel_t)`
   - external walls only: RCC chajja `box(outer_face_s, z_ffl + lintel, outer_face_s ± chajja_proj, z_ffl + lintel + chajja_t)` where `outer_face_s` is the strip edge farther from the building-extent midpoint, projecting outward.
   Use `strip.difference(gap_box)`; iterate resulting `Polygon`/`MultiPolygon` via `.geom_type` dispatch.
3. Floor/roof slabs: for each level `z_ffl(i+1)` and `roof_z`: RCC band `box(S_MIN, z − slab_t, S_MAX, z)` where `S_MIN/S_MAX` = outer faces of the outermost cut external-wall intervals on GF.
4. Foundation per GF cut wall interval: wall continues `box(s0, gl − fd + footing_t, s1, z_ffl0)` as brick (below-FFL stem), PCC footing `box(mid − fw/2, gl − fd, mid + fw/2, gl − fd + footing_t)`.
5. Earth: two hatched GL strips `box(S_MIN − 1.0, gl − 0.3, S_MIN, gl)` and `box(S_MAX, gl − 0.3, S_MAX + 1.0, gl)` material `earth`, plus plinth fill `box(S_MIN, gl, S_MAX, 0.0)` clipped by `.difference()` of all wall/footing polys, material `earth`, `cut=True`.
6. Parapet: at both outermost external strips on the roof: brick `box(s_edge0, roof_z, s_edge0 + vs.parapet_t_m, roof_z + parapet_h)` (inner edge aligned to wall face).
7. Stair profile (RCC, cut): from GF `FloorDrawing.stair` + stair room's `room_interval`. `n_r = round(ftf / vs.stair_riser_m)`; `riser = ftf / n_r`; ascending in the direction of `StairGeometry.arrow` projected on the line; cap treads at what fits the room interval. Steps polygon:

```python
def _stair_profile(s0: float, direction: int, n_risers: int, riser: float,
                   tread: float, waist: float) -> Polygon:
    pts: list[tuple[float, float]] = [(s0, 0.0)]
    s, z = s0, 0.0
    for i in range(n_risers):
        z += riser
        pts.append((s, z))
        if i < n_risers - 1:
            s += direction * tread
            pts.append((s, z))
    wv = waist * 1.4  # vertical offset of sloped waist underside
    pts += [(s, z - wv), (s0, -wv)]
    return Polygon(pts)
```

Annotate near the profile: label `f"{n_risers}R @ {round(riser * 1000)}"`.
8. Room labels: `room_interval()` per room per floor → `(mid, z_ffl + 1.5, room.name.upper())`.
9. Levels (place at `s = S_MAX + 0.6`): GL (`fmt_level(gl)` prefixed `G.L. `), `±0.00`, each upper FFL, roof, parapet top.
10. VDims (left side): `(gl − fd, gl)`, `(gl, 0)`, `(0, ftf)`, per-floor, `(roof_z, roof_z + parapet_h)` — labels in mm (`"900"`, `"450"`, `"3000"`, `"1000"`).
11. `bounds` from union of everything padded 1.2 m for annotations.

- [ ] **Step 1: Write the failing tests** (append to `test_section_geometry.py`)

```python
from app.engine.section_geometry import derive_section
from app.engine.vertical_standards import VS


def test_derive_section_structure():
    sd = derive_section(_layout(), CFG)
    assert sd.title == "SECTION A-A"
    mats = {p.material for p in sd.polys}
    assert {"brick", "rcc", "pcc", "earth"} <= mats
    z_top = max(p.poly.bounds[3] for p in sd.polys)
    assert abs(z_top - (2 * VS.floor_to_floor_m + VS.parapet_h_m)) < 0.01
    z_bot = min(p.poly.bounds[1] for p in sd.polys)
    assert abs(z_bot - (-VS.plinth_h_m - VS.foundation_depth_m)) < 0.01


def test_section_has_stair_profile_and_labels():
    sd = derive_section(_layout(), CFG)
    stair_polys = [p for p in sd.polys if p.material == "rcc"
                   and len(p.poly.exterior.coords) > 10]
    assert stair_polys, "expected a stepped stair profile polygon"
    assert any("R @" in t for _, _, t in sd.labels)
    assert len([t for _, _, t in sd.labels if "R @" not in t]) >= 2


def test_section_levels_and_dims():
    sd = derive_section(_layout(), CFG)
    label_texts = [lv.label for lv in sd.levels]
    assert any("±0.00" in t for t in label_texts)
    assert any("+3.000" in t for t in label_texts)
    assert "3000" in [d.label for d in sd.vdims]
```

- [ ] **Step 2:** Run — expect FAIL (`derive_section` undefined)
- [ ] **Step 3:** Implement `derive_section()` per construction rules 1–11 above (≈150 lines)
- [ ] **Step 4:** Run `uv run pytest tests/test_section_geometry.py -v` — expect PASS
- [ ] **Step 5:** `ruff format`/`check`, commit: `feat(engine): derive_section — canonical SectionDrawing through staircase`

---

### Task 4: `ElevationDrawing` + `derive_elevation()`

**Agent model:** sonnet

**Files:**
- Modify: `backend/app/engine/section_geometry.py` (extend)
- Test: `backend/tests/test_section_geometry.py` (extend)

**Interfaces:**
- Consumes: `cfg.road_side` (`models.py:96`, compass `"N"|"S"|"E"|"W"`), `build_floor_drawing`, `buildable_polygon`, `VS`.
- Produces:

```python
@dataclass
class ElevationDrawing:
    title: str                                   # "FRONT ELEVATION"
    silhouette: Polygon                          # facade outline GL→parapet top
    openings: list[Polygon]                      # thin-outline door/window/vent rects
    chajjas: list[Polygon]                       # thin bands above openings
    ref_lines: list[tuple[float, float, float, float]]  # dashed FFL lines (s1,z1,s2,z2)
    levels: list[LevelMark]
    vdims: list[VDim]                            # incl. overall height GL→parapet top
    gl_z: float
    bounds: tuple[float, float, float, float]

def derive_elevation(layout: Layout, cfg: PlotConfig, vs: VerticalStandards = VS) -> ElevationDrawing
```

**Construction rules:**
1. Facade = building edge facing `cfg.road_side`. Facade axis `u`: for `"S"`/`"N"` road the facade runs along x (u = x); for `"E"`/`"W"` along y. Facade boundary coordinate `v_front` = the buildable bound on the road side (S → miny, N → maxy, W → minx, E → maxx).
2. Silhouette: `box(u_min, gl, u_max, roof_z + parapet_h)` where `u_min/u_max` from buildable bounds on the facade axis; `gl = -vs.plinth_h_m`.
3. Openings per floor: from that floor's `FloorDrawing.openings`, keep those on the facade external wall: orientation matches (S/N road → `op.is_horizontal is True`; E/W → False) and distance of `(cx, cy)` to `v_front` < 0.3 m. Rect: `box(u_c − w/2, z_lo, u_c + w/2, z_hi)` with `z_lo/z_hi` per kind exactly as Task 3 rule 2 (door from `z_ffl`, window from sill, ventilator from vent sill; all to lintel — doors to `door_h`).
4. Chajja band above every facade opening: `box(u_c − w/2 − 0.15, z_ffl + lintel, u_c + w/2 + 0.15, z_ffl + lintel + chajja_t)`.
5. Ref lines (thin dashed): at `z = 0.0` (plinth/FFL line), each upper FFL, `roof_z`.
6. Levels at `s = u_max + 0.6`: GL, ±0.00, upper FFLs, parapet top. VDims: one overall `(gl, roof_z + parapet_h)` labeled in mm, plus `(gl, 0)` plinth.
7. If NO facade openings found (road-side wall may be blank in some archetypes), still return the silhouette + levels — never raise.

- [ ] **Step 1: Failing tests**

```python
from app.engine.section_geometry import derive_elevation


def test_derive_elevation_silhouette_and_levels():
    ed = derive_elevation(_layout(), CFG)
    assert ed.title == "FRONT ELEVATION"
    minx, miny, maxx, maxy = ed.silhouette.bounds
    assert abs(maxy - (2 * VS.floor_to_floor_m + VS.parapet_h_m)) < 0.01
    assert abs(miny - (-VS.plinth_h_m)) < 0.01
    assert any("±0.00" in lv.label for lv in ed.levels)
    total_mm = round((2 * VS.floor_to_floor_m + VS.parapet_h_m + VS.plinth_h_m) * 1000)
    assert str(total_mm) in [d.label for d in ed.vdims]


def test_elevation_openings_inside_silhouette():
    ed = derive_elevation(_layout(), CFG)
    for rect in ed.openings:
        assert rect.within(ed.silhouette.buffer(0.01))
    for rect in ed.openings:
        assert rect.bounds[3] <= 2 * VS.floor_to_floor_m + 0.01
```

- [ ] **Step 2:** Run — expect FAIL
- [ ] **Step 3:** Implement `derive_elevation()` per rules 1–7 (≈80 lines)
- [ ] **Step 4:** Run `uv run pytest tests/test_section_geometry.py -v` — expect PASS
- [ ] **Step 5:** `ruff format`/`check`, commit: `feat(engine): derive_elevation — front elevation drawing model`

---

### Task 5: `section_render.py` — ReportLab renderer (hatches, levels, dims)

**Agent model:** opus

**Files:**
- Create: `backend/app/engine/section_render.py`
- Test: `backend/tests/test_section_render.py`

**Interfaces:**
- Consumes: `SectionDrawing`, `ElevationDrawing`, `LevelMark`, `VDim` from Task 3/4.
- Produces:
  - `render_section_view(c: Canvas, sd: SectionDrawing, region: tuple[float, float, float, float]) -> float` — draws into page region `(x, y, w, h)` in points, scale-to-fit, returns the metres→points scale used
  - `render_elevation_view(c: Canvas, ed: ElevationDrawing, region: tuple[float, float, float, float]) -> float`
  - `draw_section_marker(c: Canvas, x1: float, y1: float, x2: float, y2: float, label: str = "A") -> None` — chain line (dash `6 2 1 2`), thick 8 pt end strokes, arrowheads perpendicular (view direction), bold `label` at both ends — for use on plan pages (page-space points)
  - `hatch_polygon(c: Canvas, pts: list[tuple[float, float]], material: str, spacing_pt: float = 5.0) -> None`

**Implementation notes (follow exactly):**
- Line weights: cut outline `1.4`, thin/annotation `0.5` (matches EXT_LW/DIM_LW convention in `pdf.py:165-176`).
- `hatch_polygon`: `c.saveState()`; build path from `pts`, `c.clipPath(path, stroke=0, fill=0)`; then per material draw across the bbox: `brick` 45° lines every `spacing_pt`; `rcc` 45° + 135°; `pcc` dot grid (`c.circle(..., 0.4, fill=1)` every `spacing_pt`); `earth` short 60° dashes on staggered rows; `c.restoreState()`.
- Level marker: 5 pt solid right triangle with tip on the level line + `Helvetica 6` text; VDim: vertical extension lines + tick ends (match `_draw_dimension_lines` style in `pdf.py:852-949` — read it first and mirror the tick/typeface conventions).
- Both views: compute `scale = min(w/s_extent, h/z_extent) * 0.92`, centre in region, draw a graphic scale bar (copy the 1 m-segment pattern of `_draw_scale_bar`, `pdf.py:962-987` — reimplement locally ~20 lines, do NOT import from `pdf.py` [circular import]) and the title text `sd.title` + computed ratio: `ratio = round((72 / 0.0254) / scale_pt_per_m)` rendered as `SCALE 1:{ratio}`.
- Elevation: ground line thick, silhouette outline 1.0, openings/chajjas 0.5 thin outline, ref lines dashed `c.setDash(3, 3)`.
- Everything strictly black on white (`c.setStrokeColorRGB(0, 0, 0)`, fills white or black only).

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_section_render.py
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.engine.generator import generate
from app.engine.models import PlotConfig
from app.engine.section_geometry import derive_elevation, derive_section
from app.engine.section_render import render_elevation_view, render_section_view
from app.quality.pdf_image import pdf_page_png
from tests.helpers import mean_saturation  # verify actual import path in test_render_helpers.py

CFG = PlotConfig(
    plot_length=12.0, plot_width=9.0,
    setback_front=3.0, setback_rear=1.5, setback_left=1.0, setback_right=1.0,
    num_bedrooms=2, toilets=2, parking=True,
)


def _one_page_pdf(draw) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw(c)
    c.showPage()
    c.save()
    return buf.getvalue()


def test_section_view_renders_monochrome():
    lay = generate(CFG)[0]
    sd = derive_section(lay, CFG)
    pdf = _one_page_pdf(lambda c: render_section_view(c, sd, (40, 120, 515, 620)))
    png = pdf_page_png(pdf, 0)
    assert mean_saturation(png) < 0.02


def test_elevation_view_renders():
    lay = generate(CFG)[0]
    ed = derive_elevation(lay, CFG)
    pdf = _one_page_pdf(lambda c: render_elevation_view(c, ed, (40, 120, 515, 620)))
    assert pdf[:4] == b"%PDF"
```

(Adjust the `mean_saturation` import to wherever `test_render_helpers.py` actually gets it from — read that file first.)

- [ ] **Step 2:** Run — expect FAIL
- [ ] **Step 3:** Implement `section_render.py` (≈220 lines) per implementation notes
- [ ] **Step 4:** Run `uv run pytest tests/test_section_render.py -v` — expect PASS
- [ ] **Step 5 (visual checkpoint):** Render both views of the fixture layout to `$CLAUDE_JOB_DIR/tmp/section_preview.png` / `elevation_preview.png` via `pdf_page_png`, and **show them to Karthik for approval before proceeding** (standing rule: show generated drawing artifacts before applying)
- [ ] **Step 6:** `ruff format`/`check`, commit: `feat(engine): ReportLab renderer for section/elevation views (IS 962 hatching)`

---

### Task 6: Wire into standard PDF (4 → 6 pages) + section markers on plans

**Agent model:** sonnet

**Files:**
- Modify: `backend/app/engine/pdf.py` — `render_pdf()` (`pdf.py:181-223`): after the structural loop add the two pages; `_draw_floor_projected()` (`pdf.py:1707+`): draw the A-A marker on architectural plan pages
- Test: `backend/tests/test_pdf_section_pages.py`

**Interfaces:**
- Consumes: `derive_section`, `derive_elevation`, `render_section_view`, `render_elevation_view`, `draw_section_marker`, `section_cut_line`.
- Produces: standard PDF page order becomes: 1 GF plan, 2 FF plan, 3 GF structural, 4 FF structural, **5 SECTION A-A, 6 FRONT ELEVATION** — update the `render_pdf` docstring (`pdf.py:190-195`).

**Page composition** (mirror how existing pages are laid out — title block bottom, view above; read the structural-page composition first and reuse its exact margin/title-block invocation — the region constants below are indicative):

```python
    # ── Section & elevation pages ─────────────────────────────────────────────
    sd = derive_section(layout, cfg)
    render_section_view(c, sd, (MARGIN, TITLE_H + 30, PAGE_W - 2 * MARGIN, PAGE_H - TITLE_H - 60))
    # then the same _draw_title_block(...) call the structural pages make
    c.showPage()
    ed = derive_elevation(layout, cfg)
    render_elevation_view(c, ed, (MARGIN, TITLE_H + 30, PAGE_W - 2 * MARGIN, PAGE_H - TITLE_H - 60))
    # same _draw_title_block(...) call
    c.showPage()
```

**Section marker on plan pages:** inside `_draw_floor_projected`, after walls are drawn, compute `line, along_y = section_cut_line(floor_plan.rooms, buildable_polygon(cfg))`, transform the line's two endpoints with the SAME plot→page transform used for walls in that function, and call `draw_section_marker(c, x1, y1, x2, y2, "A")`.

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_pdf_section_pages.py
from app.engine.generator import generate
from app.engine.models import PlotConfig
from app.engine.pdf import render_pdf
from tests.helpers import pdf_page_count, pdf_page_text  # match test_render_helpers.py imports

CFG = PlotConfig(
    plot_length=12.0, plot_width=9.0,
    setback_front=3.0, setback_rear=1.5, setback_left=1.0, setback_right=1.0,
    num_bedrooms=2, toilets=2, parking=True,
)


def _pdf() -> bytes:
    lay = generate(CFG)[0]
    return render_pdf("Test Project", lay, CFG, 2)


def test_standard_pdf_has_six_pages():
    assert pdf_page_count(_pdf()) == 6


def test_section_page_content():
    text = pdf_page_text(_pdf(), 4).upper()
    assert "SECTION A-A" in text
    assert "SCALE" in text


def test_elevation_page_content():
    text = pdf_page_text(_pdf(), 5).upper()
    assert "FRONT ELEVATION" in text
    assert "SCALE" in text
```

(Verify helper names in `tests/helpers/` first; use whatever `test_render_helpers.py` uses for page count/text.)

- [ ] **Step 2:** Run — expect FAIL (page count 4)
- [ ] **Step 3:** Implement the wiring + marker
- [ ] **Step 4:** Run `uv run pytest tests/test_pdf_section_pages.py tests/test_render_helpers.py tests/test_ccqs.py -v` — expect PASS
- [ ] **Step 5:** `ruff format`/`check`, commit: `feat(pdf): add SECTION A-A and FRONT ELEVATION pages with plan cut markers`

---

### Task 7: Wire into approval PDF (replace schematic section, add elevation → 5 pages)

**Agent model:** sonnet

**Files:**
- Modify: `backend/app/engine/approval_pdf.py` — `generate_approval_pdf()` (`approval_pdf.py:68-99`); `_draw_section_and_title_block()` (`approval_pdf.py:726-755`); DELETE `_draw_section_view()` (`approval_pdf.py:757-930`); add `_draw_elevation_and_title_block()`; add A-A marker in `_draw_approval_floor_plan()` (`approval_pdf.py:479-593`) same as Task 6
- Test: `backend/tests/test_approval_section_pages.py`

**Changes:**
1. `_draw_section_and_title_block`: replace the `_draw_section_view(...)` call with `derive_section(layout, plot_config)` + `render_section_view(c, sd, region)` (region = area above the professional title block; read the current function to get the exact free rect). Keep `_draw_professional_title_block` untouched.
2. New `_draw_elevation_and_title_block(c, layout, plot_config, owner_info)`: same composition with `derive_elevation` + `render_elevation_view` + `_draw_professional_title_block`.
3. `generate_approval_pdf`: add `_draw_elevation_and_title_block(...)` + `c.showPage()` after the section page; update the docstring ("5-page").
4. Delete `_draw_section_view` and its now-unused local constants (they moved to `vertical_standards.py` in Task 1).

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_approval_section_pages.py
from app.engine.approval_pdf import OwnerInfo, generate_approval_pdf
from app.engine.generator import generate
from app.engine.models import PlotConfig
from tests.helpers import pdf_page_count, pdf_page_text

CFG = PlotConfig(
    plot_length=12.0, plot_width=9.0,
    setback_front=3.0, setback_rear=1.5, setback_left=1.0, setback_right=1.0,
    num_bedrooms=2, toilets=2, parking=True,
)


def _pdf() -> bytes:
    lay = generate(CFG)[0]
    owner = OwnerInfo(owner_name="Test Owner", survey_number="123/4",
                      locality="Trichy", engineer_name="Er. Test",
                      license_number="LIC-1", municipality="Trichy Corp")
    return generate_approval_pdf(lay, CFG, owner, "A")


def test_approval_pdf_has_five_pages():
    assert pdf_page_count(_pdf()) == 5


def test_approval_section_page_is_convention_faithful():
    text = pdf_page_text(_pdf(), 3).upper()
    assert "SECTION A-A" in text
    assert "±0.00" in pdf_page_text(_pdf(), 3)


def test_approval_elevation_page():
    text = pdf_page_text(_pdf(), 4).upper()
    assert "FRONT ELEVATION" in text
```

(Check `OwnerInfo`'s real fields in `approval_pdf.py` before writing — the constructor above follows the route schema in `export.py:121-161` but must be verified.)

- [ ] **Step 2:** Run — expect FAIL
- [ ] **Step 3:** Implement changes 1–4
- [ ] **Step 4:** Run `uv run pytest tests/test_approval_section_pages.py tests/test_approval_site_plan.py -v` — expect PASS (site-plan page-0 tests must be untouched)
- [ ] **Step 5:** `ruff format`/`check`, commit: `feat(approval-pdf): convention-faithful SECTION A-A + FRONT ELEVATION pages`

---

### Task 8: Quality gates — CCQS baseline, full suite, docs

**Agent model:** haiku

**Files:**
- Possibly modify: CCQS baseline JSON (find via `test_ccqs_gate.py:12-33` — `FIXTURE`/baseline paths under `tests/fixtures/`)
- Modify: `Status.md` (progress log), `CLAUDE.md` "PDF Output" bullet (now 6-page standard / 5-page approval)

- [ ] **Step 1:** Run `uv run pytest tests/test_ccqs_gate.py -v`. Expected: PASS unchanged (monochromaticity uses page 0 only; text scores are capped counts and currently saturated at 80/80). If it fails, inspect which component moved and regenerate the committed baseline JSON following the procedure in that test file's comments — do not loosen tolerances.
- [ ] **Step 2:** Run the full backend suite: `uv run pytest` — expect all green (fix any collateral test expecting 4 pages)
- [ ] **Step 3:** `uv run ruff format . && uv run ruff check .` — clean
- [ ] **Step 4:** Update `Status.md` + the `CLAUDE.md` PDF Output section; `graphify update .`
- [ ] **Step 5:** Commit: `chore: update CCQS baseline, docs for section/elevation pages` (only include baseline if it actually changed)
- [ ] **Step 6:** STOP. Propose `finish-feature` workflow to Karthik by name (tests → pre-push → PR → CI) and wait for explicit go-ahead (Workflow tool needs his opt-in per standing rule).

---

## Out of scope (explicitly deferred — do not implement)

- Section B-B (cross section), rear/side elevations
- DXF export of section/elevation (PDF only for now)
- Frontend `section-view-svg.tsx` upgrade to match (it already has its own simpler section; sync later)
- Beyond-the-cut-plane thin-outline openings/walls inside the section (IS-nice-to-have; MVP shows cut elements + stair + slabs + labels)
- Mumty/stair headroom cabin above terrace; basement/stilt floors in section (fallback: sections cover ground/first/second floors present in `Layout`)
- Opening height fields on the `Opening` dataclass (heights come from `VerticalStandards` by kind — no schema change)

## Verification (end-to-end)

1. `cd backend && uv run pytest` — full suite green.
2. Generate both PDFs for the fixture config, rasterize pages 5/6 (standard) and 4/5 (approval) via `pdf_page_png`, and visually confirm: stair steps profile visible, brick hatch on cut walls, RCC crosshatch on slabs/lintels, level markers `±0.00…+7.000`, chain-line A-A marker on plan pages. Show the PNGs to Karthik (approval checkpoint, matches Task 5 step 5).
3. CCQS: `uv run pytest tests/test_ccqs_gate.py` still ≥ baseline (80/80 expected).
4. After merge + Cloud Run deploy, hit `GET /projects/{id}/export/pdf` on staging (`v2` lane) and eyeball the real output.

## Research reference (for the implementer)

Key conventions distilled from IS 962:1989 + Indian bye-law research (full sourced report in the planning conversation, 2026-07-10): cut through staircase is the municipal baseline; cut elements = thick outline (≥2:1 vs thin) + material hatch (brick 45°, RCC crosshatch, PCC dots, earth stipple); levels as `±0.00` datum at GF FFL with `+/-` prefixes; one section + one front elevation at 1:100 is the mandatory minimum; FAR-relevant height = GL → parapet top.
