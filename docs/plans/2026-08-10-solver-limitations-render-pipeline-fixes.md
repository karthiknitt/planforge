# Solver-Limitations Render Pipeline Fixes — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix every actionable bug/feature catalogued in `docs/superpowers/specs/solver_limitations.md` (2026-08-09) in `backend/app/engine/` — multi-floor PDF emission, exterior-wall ring derivation, stair-less floor crash, parking door protection, stair orientation/labels, entrance-placement diagnostics, plot-dimension validation, and new RoomTypes (foyer/courtyard/wardrobe).

**Architecture:** All fixes are inside the existing geometry→drawing pipeline (`plan_geometry.py` → `cad_elements.FloorDrawing` → `pdf.py`/`section_geometry.py`). Diagnostics are surfaced via a new additive `FloorDrawing.diagnostics` field (flows into persisted drawing dicts via the existing `to_dict()` passthrough — no schema migration). No solver (CP-SAT) behavior changes.

**Tech Stack:** Python 3.12, Shapely, ReportLab, FastAPI backend at `backend/`. Tests: pytest via `backend/.venv/bin/pytest`. Commits: Conventional Commits (`fix(engine): …`, `feat(engine): …`), matching `git log` style.

**Source spec:** `docs/superpowers/specs/solver_limitations.md` — every code anchor below was verified against the working tree on 2026-08-10. Line numbers will drift as tasks land; re-locate by symbol name.

**Repo policy:** ask the user before the first `git commit` (no git mutations without explicit approval), then commit per task.

---

## Scope map

| Spec item | Description | Plan task |
|---|---|---|
| #3 / H | `section_cut_line()` crashes on stair-less floor | Task 1 |
| #2 | Parking rooms get interior doors | Task 2 |
| #6a | `render_pdf()` silently drops second floor + basement (**HIGH SEVERITY**) | Task 3 |
| #6c | External wall ring from buildable bounds, not room union | Task 4 |
| #1 + #5 | Stair treads S→N only; label always "UP" | Task 5 |
| #6, #6b, G, #6d | Main entrance fails silently (4 root causes, one epic) | Task 6 |
| F | `plot_width`/`plot_length` naming trap → validation warning | Task 7 |
| C | No RoomType for foyer / courtyard / wardrobe | Task 8 (+ optional Task 9 frontend) |
| J + workaround-6 | Harness area-reporting + dyadic snap | Task 10 (optional) |
| — | Resolution addendum in the spec doc | Task 11 |

**Explicit non-goals** (per the spec doc itself):
- #4 (room-graph connectivity check) — explicitly deferred to the layout-quality critique-loop spec (`docs/superpowers/specs/2026-08-09-layout-quality-critique-loop-design.md`). Not fixed here.
- A / B — `Room` rectangle-only and solver-input-shaped `PlotConfig` fields are accepted schema limits.
- D / E — reconstruction methodology notes, nothing to fix in code.
- Renaming `PlotConfig.plot_width`/`plot_length` — too invasive; the doc's fallback option (validation warning) is chosen instead.
- #6d *placement* redesign (door on stair landing for porch-fronted typologies) — diagnostics only, per the doc's "consolidated entrance-placement epic" guidance.
- Solver/archetypes *generating* foyer/courtyard/wardrobe rooms (`room_specs.json`, `archetypes.py`) — the new types are for hand-authored/reconstruction data and the interactive editor; solver generation is a follow-up if ever wanted.
- Structural/section/elevation content redesign — spec scope is architectural pages + the structural page loop count.

**Run all backend tests after every task:** `cd /home/karthik/projects/PlanForge/backend && .venv/bin/pytest -q`

---

## Task 1: `section_cut_line()` falls back gracefully when a floor has no staircase (#3, H)

**Files:**
- Modify: `backend/app/engine/section_geometry.py:24-32` (`section_cut_line`)
- Test: `backend/tests/test_section_geometry.py`

**Step 1: Write the failing test**

Append to `backend/tests/test_section_geometry.py` (follow its existing import/fixture style; add missing imports at top):

```python
def test_section_cut_line_falls_back_without_staircase():
    from shapely.geometry import box

    from app.engine.section_geometry import section_cut_line
    from tests.test_multi_floor import _room

    rooms = [_room("living", "living", 1.13, 1.73, 4.0, 5.0)]
    buildable = box(1.0, 2.0, 10.0, 14.0)
    line, along_y = section_cut_line(rooms, buildable)
    # graceful fallback: plain vertical mid-line through the buildable bounds
    assert along_y is True
    coords = list(line.coords)
    assert coords[0][0] == coords[1][0] == 5.5
    assert coords[0][1] == 1.0 and coords[1][1] == 15.0  # padded by 1.0


def test_render_pdf_handles_stairless_ground_floor():
    """End-to-end: a genuinely stair-less single-story home renders (H)."""
    from app.engine.pdf import render_pdf
    from tests.test_multi_floor import _cfg, _make_layout, _room

    rooms = [  # front rooms at 1.73 = setback_front(1.5) + EWT(0.23)
        _room("living", "living", 1.13, 1.73, 4.0, 5.0),
        _room("bed", "bedroom", 5.13, 1.73, 4.0, 5.0),
    ]
    lay = _make_layout(rooms, ff_rooms=[])
    pdf = render_pdf("Stairless", lay, _cfg(), 3)
    from tests.helpers.pdf_png import pdf_pages

    assert pdf_pages(pdf) == 6
```

**Step 2: Run test to verify it fails**

Run: `cd /home/karthik/projects/PlanForge/backend && .venv/bin/pytest tests/test_section_geometry.py -v -k "falls_back or stairless"`
Expected: FAIL with `StopIteration` raised from `section_cut_line`.

**Step 3: Implement**

In `backend/app/engine/section_geometry.py`, replace lines 24-32:

```python
def section_cut_line(rooms: list[Room], buildable: Polygon) -> tuple[LineString, bool]:
    stair = next((r for r in rooms if r.type == "staircase"), None)
    minx, miny, maxx, maxy = buildable.bounds
    if stair is None:
        # stair-less floor (single-story home, terrace-only top floor) —
        # fall back to a plain vertical mid-line rather than crashing.
        cx = (minx + maxx) / 2
        return LineString([(cx, miny - 1.0), (cx, maxy + 1.0)]), True
    along_y = stair.depth >= stair.width
    if along_y:
        cx = stair.x + stair.width / 2
        return LineString([(cx, miny - 1.0), (cx, maxy + 1.0)]), True
    cy = stair.y + stair.depth / 2
    return LineString([(minx - 1.0, cy), (maxx + 1.0, cy)]), False
```

**Step 4: Run test to verify it passes**

Run: `cd /home/karthik/projects/PlanForge/backend && .venv/bin/pytest tests/test_section_geometry.py -v`
Expected: PASS (new + existing).

Note: `section_geometry.py:300` cuts on **ground-floor** rooms, so this fix covers a stair-less GF. If the render test instead crashes while drawing the EMPTY first-floor page, that is a separate small gap: `_draw_floor_projected`'s wall block is already guarded by `if rooms:` (`pdf.py:434`), but `_draw_dimension_lines` / `_draw_structural_floor` may not be — add a minimal early-return for empty `floor_plan.rooms` there as part of this task.

**Step 5: Commit**

```bash
git add backend/app/engine/section_geometry.py backend/tests/test_section_geometry.py
git commit -m "fix(engine): fall back to mid-line section cut when floor has no staircase (#3)"
```

---

## Task 2: Parking rooms never host an interior door (#2)

**Files:**
- Modify: `backend/app/engine/plan_geometry.py:67-68` (type sets) and `:785-787` (door loop)
- Test: `backend/tests/test_plan_openings.py`

**Step 1: Write the failing test**

Append to `backend/tests/test_plan_openings.py`:

```python
def test_parking_never_hosts_interior_door():
    # _cfg_9x15 plate front: x 1.23 (=1.0+0.23), y 1.73 (=1.5+0.23)
    rooms = [
        _room("living", 1.23, 1.73, 3.5, 5.0),
        _room("porch", 1.23, 6.73, 3.5, 3.0, rtype="parking"),
    ]
    openings, _walls = _openings_for(rooms, _cfg_9x15())
    porch_doors = [
        o
        for o in openings
        if o.kind == "door" and o.swing_into_room_id == "porch"
    ]
    assert porch_doors == []
```

**Step 2: Run test to verify it fails**

Run: `cd /home/karthik/projects/PlanForge/backend && .venv/bin/pytest tests/test_plan_openings.py::test_parking_never_hosts_interior_door -v`
Expected: FAIL — today parking goes through the per-room door loop and can get a door.

**Step 3: Implement**

In `backend/app/engine/plan_geometry.py`, add next to `_PARKING_TYPES` (line 68):

```python
_PARKING_TYPES = {"parking", "parking_4w", "parking_2w"}
# rooms that never host their own interior door: circulation, open-air/outdoor,
# and transitional spaces — doors serving them are placed by their neighbours.
_NO_DOOR_TYPES = _PARKING_TYPES | {"passage"}
```

Change the door loop (lines 785-787):

```python
    for idx, room in sorted(enumerate(rooms), key=lambda t: t[1].id):
        if room.type in _NO_DOOR_TYPES:
            continue
```

Note: this does NOT remove porch→house entry realism — the neighbouring room (e.g. living) still places a door on the shared wall, swinging into itself. `garage` deliberately stays door-eligible (it is enclosed, unlike an open porch).

**Step 4: Run tests**

Run: `cd /home/karthik/projects/PlanForge/backend && .venv/bin/pytest tests/test_plan_openings.py tests/test_plan_geometry.py tests/test_stair_wet_separation.py -v`
Expected: all PASS. Then full suite: `.venv/bin/pytest -q`.

**Step 5: Commit**

```bash
git add backend/app/engine/plan_geometry.py backend/tests/test_plan_openings.py
git commit -m "fix(engine): parking rooms never host their own interior door (#2)"
```

---

## Task 3: `render_pdf()` emits second-floor and basement pages (#6a — HIGH SEVERITY)

**Files:**
- Modify: `backend/app/engine/pdf.py:246-306` (`render_pdf` page loops + docstring)
- Test: `backend/tests/test_pdf_multi_floor_pages.py` (new)

**Step 1: Write the failing test**

Create `backend/tests/test_pdf_multi_floor_pages.py`:

```python
"""Page emission for G+2 / basement layouts (solver_limitations #6a)."""

from app.engine.pdf import render_pdf

from tests.helpers.pdf_png import pdf_page_text, pdf_pages
from tests.test_multi_floor import _cfg, _make_layout, _room


def _stack(sf=False, basement=False):
    gf = [
        _room("living", "living", 1.13, 1.73, 4.0, 5.0),
        _room("stair", "staircase", 5.13, 1.73, 2.0, 5.0),
        _room("bed", "bedroom", 7.13, 1.73, 2.84, 5.0),
    ]
    ff = [  # same footprint — free column-grid cross-check
        _room("bed1", "bedroom", 1.13, 1.73, 4.0, 5.0),
        _room("stair1", "staircase", 5.13, 1.73, 2.0, 5.0),
        _room("bed2", "bedroom", 7.13, 1.73, 2.84, 5.0),
    ]
    sf_rooms = [
        _room("bed3", "bedroom", 1.13, 1.73, 4.0, 5.0),
        _room("stair2", "staircase", 5.13, 1.73, 2.0, 5.0),
        _room("bed4", "bedroom", 7.13, 1.73, 2.84, 5.0),
    ]
    basement_rooms = [_room("hall", "gym", 1.13, 1.73, 8.84, 5.0)]
    return _make_layout(
        gf_rooms=gf,
        ff_rooms=ff,
        sf_rooms=sf_rooms if sf else None,
        basement_rooms=basement_rooms if basement else None,
    )


def test_g2_pdf_has_second_floor_pages():
    pdf = render_pdf("G+2", _stack(sf=True), _cfg(), 3)
    assert pdf_pages(pdf) == 8  # SF-arch + SF-structural in addition to 6
    assert "SECOND FLOOR" in pdf_page_text(pdf, 2).upper()  # SF architectural
    assert "SECOND FLOOR" in pdf_page_text(pdf, 5).upper()  # SF structural


def test_g1_basement_pdf_has_basement_pages():
    pdf = render_pdf("G+1+Basement", _stack(basement=True), _cfg(), 3)
    assert pdf_pages(pdf) == 8
    assert "BASEMENT" in pdf_page_text(pdf, 0).upper()  # basement architectural
    assert "BASEMENT" in pdf_page_text(pdf, 3).upper()  # basement structural


def test_g1_still_six_pages():  # regression guard — existing behaviour unchanged
    pdf = render_pdf("G+1", _stack(), _cfg(), 3)
    assert pdf_pages(pdf) == 6
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/karthik/projects/PlanForge/backend && .venv/bin/pytest tests/test_pdf_multi_floor_pages.py -v`
Expected: FAIL — page counts 6, no SECOND FLOOR/BASEMENT text.

**Step 3: Implement**

In `backend/app/engine/pdf.py`:

Add module-level helpers just above `render_pdf` (line ~243, under `_available_width`):

```python
_FLOOR_LABELS = {-1: "Basement", 0: "Ground Floor", 1: "First Floor", 2: "Second Floor"}


def _floor_label(floor_plan) -> str:
    return _FLOOR_LABELS.get(floor_plan.floor, f"Floor {floor_plan.floor}")


def _ordered_floors(layout: Layout) -> list:
    """All populated floors in build order (basement first)."""
    return [
        fp
        for fp in (
            layout.basement_floor,
            layout.ground_floor,
            layout.first_floor,
            layout.second_floor,
        )
        if fp is not None
    ]
```

Replace both page loops (lines 277-306) and update the docstring page list:

```python
    # ── Architectural pages ────────────────────────────────────────────────────
    for floor_plan in _ordered_floors(layout):
        _draw_floor_projected(
            c, floor_plan, layout, cfg, project_name, num_bedrooms,
            _floor_label(floor_plan),
            annotations=annotations, watermark_preliminary=show_watermark,
        )
        c.showPage()

    # ── Structural pages ───────────────────────────────────────────────────────
    for floor_plan in _ordered_floors(layout):
        _draw_structural_floor(
            c, floor_plan, layout, cfg, project_name, num_bedrooms,
            _floor_label(floor_plan),
            structural_design=structural_design,
        )
        c.showPage()
```

(New docstring page order: "1..N. Architectural pages, one per populated floor, basement first · N+1..2N. Structural pages, same order · then Section A-A · Front Elevation".)

**Step 4: Run tests**

Run: `cd /home/karthik/projects/PlanForge/backend && .venv/bin/pytest tests/test_pdf_multi_floor_pages.py tests/test_pdf_section_pages.py tests/test_pdf_page_composition.py tests/test_multi_floor.py -v`
Expected: PASS, including the existing six-page test (G+1 output unchanged).

**Step 5: Visual verification**

Run a throwaway render with `_stack(sf=True, basement=True)`, dump pages 0/2/3/5 via `tests.helpers.pdf_png.render_page_png` to `/tmp/opencode/`, and read the PNGs — confirm the basement structural page draws beams/columns sanely (`_draw_structural_floor` was never exercised for `floor=-1` in production).

**Step 6: Commit**

```bash
git add backend/app/engine/pdf.py backend/tests/test_pdf_multi_floor_pages.py
git commit -m "fix(engine): render second-floor and basement pages in render_pdf (#6a)"
```

---

## Task 4: External wall ring derives from the floor's room union, not buildable bounds (#6c)

**Files:**
- Modify: `backend/app/engine/plan_geometry.py:186-208` (`derive_walls`)
- Test: `backend/tests/test_plan_geometry.py`

**Step 0: Pre-change baseline (do first)**

Run a snapshot script and save output for later diffing:

```bash
cd /home/karthik/projects/PlanForge/backend && .venv/bin/python - <<'EOF'
from app.engine.plan_geometry import build_floor_drawing
from tests.helpers.golden import golden_config, golden_layout
d = build_floor_drawing(golden_layout().ground_floor, golden_config()).to_dict()
import json; open('/tmp/walls_baseline.json','w').write(json.dumps(d['walls'], indent=1))
print(len(d['walls']), 'walls')
EOF
```

**Step 1: Write the failing test**

Append to `backend/tests/test_plan_geometry.py`:

```python
def test_external_ring_follows_room_union_not_buildable():
    # rooms cover only the FRONT half of the _cfg_9x15 plate — roof void at rear
    rooms = [
        _room("living", 1.23, 1.73, 4.0, 4.0),
        _room("stair", 5.23, 1.73, 2.0, 4.0, rtype="staircase"),
    ]
    buildable = buildable_polygon(_cfg_9x15())
    walls = derive_walls(rooms, buildable)
    ext = [w for w in walls if w.kind == "external"]
    rear_cyt = max(max(w.y1, w.y2) for w in ext)
    front_cyb = min(min(w.y1, w.y2) for w in ext)
    # ring hugs the room union (5.73 + EWT/2), NOT the buildable rear edge
    assert rear_cyt == pytest.approx(5.73 + EWT / 2, abs=1e-6)
    assert front_cyb == pytest.approx(1.73 - EWT / 2, abs=1e-6)


def test_external_ring_falls_back_to_buildable_without_rooms():
    buildable = buildable_polygon(_cfg_9x15())
    walls = derive_walls([], buildable)
    assert [w for w in walls if w.kind == "external"]
```

(Import `pytest` at top if missing — check the file's existing imports first.)

**Step 2: Run test to verify it fails**

Run: `cd /home/karthik/projects/PlanForge/backend && .venv/bin/pytest tests/test_plan_geometry.py -k external_ring -v`
Expected: FAIL — rear ring sits at the buildable rear edge, not 5.73 + EWT/2.

**Step 3: Implement**

In `derive_walls` (`plan_geometry.py:186-208`), derive the plate bounds from the room union when rooms exist. Import `box` and `unary_union` (check the file's existing shapely imports at top; add to that import list). Replace lines 193-208:

```python
    if rooms:
        footprint = unary_union(
            [box(r.x, r.y, r.x + r.width, r.y + r.depth) for r in rooms]
        )
        px1, py1, px2, py2 = footprint.bounds
        if abs(footprint.area - (px2 - px1) * (py2 - py1)) > 1e-6:
            logger.warning(
                "non-rectangular room footprint: external ring approximated "
                "by the footprint bounding box (jogged outline not followed)"
            )
    else:
        bx1, by1, bx2, by2 = buildable.bounds
        px1, py1, px2, py2 = bx1 + ewt, by1 + ewt, bx2 - ewt, by2 - ewt

    cxl, cxr = px1 - ewt / 2, px2 + ewt / 2
    cyb, cyt = py1 - ewt / 2, py2 + ewt / 2

    walls: list[WallSegment] = [
        WallSegment(cxl, cyb, cxr, cyb, ewt, kind="external"),
        WallSegment(cxl, cyt, cxr, cyt, ewt, kind="external"),
        WallSegment(cxl, cyb, cxl, cyt, ewt, kind="external"),
        WallSegment(cxr, cyb, cxr, cyt, ewt, kind="external"),
    ]
```

Delete the old non-rectangular-buildable warning (it warned about the *buildable* polygon; the ring no longer derives from it) — BUT first check `buildable.bounds` usage further down: lines 213-220 mark plate-boundary edges as covered using `px1/px2/py1/py2` — these now automatically mean the room-union plate, which is correct (an edge on the footprint boundary is covered by the external ring). Keep the rest of the function (orphan/paired wall logic) untouched.

**Known residual limitation (document in the code comment):** uncovered room edges facing an *interior* void (e.g. a roof void over part of the GF footprint, technically inside the footprint bounding box) are still drawn as `internal` (iwt) orphan walls. Fixing that needs Shapely strip classification of every orphan edge against the footprint; NOT in scope for this task.

**Step 4: Run tests + baseline diff**

Run: `.venv/bin/pytest tests/test_plan_geometry.py tests/test_plan_drawing.py tests/test_plan_openings.py tests/test_stair_wet_separation.py -v`
Then re-run the Step-0 snapshot script writing to `/tmp/walls_after.json` and `diff /tmp/walls_baseline.json /tmp/walls_after.json`.
Expected: PASS + **empty diff** (golden/solver layouts fill the whole plate, so union bbox == plate bbox — no visual change for solver-generated layouts). If the diff is non-empty, stop and investigate: a solver layout does NOT fill its plate, and this change alters its walls.

Then full suite: `.venv/bin/pytest -q`.

**Step 5: Commit**

```bash
git add backend/app/engine/plan_geometry.py backend/tests/test_plan_geometry.py
git commit -m "fix(engine): derive external wall ring from floor's room union (#6c)"
```

---

## Task 5: Staircase tread orientation + floor-aware UP/DN label (#1, #5)

**Files:**
- Modify: `backend/app/engine/pdf.py:732-791` (`_draw_staircase_treads`) and call site `:628`
- Test: `backend/tests/test_pdf_multi_floor_pages.py` (extend)

**Step 1: Write the failing tests**

Append to `backend/tests/test_pdf_multi_floor_pages.py`:

```python
def test_stair_label_is_floor_aware():
    from tests.helpers.pdf_png import pdf_page_text

    pdf = render_pdf("G+1", _stack(), _cfg(), 3)
    assert "UP" in pdf_page_text(pdf, 0)  # ground floor: floor exists above
    assert "DN" in pdf_page_text(pdf, 1)  # first (top) floor


def test_stair_tread_geometry_east_west():
    from app.engine.pdf import _stair_tread_elements

    room = _room("stair", "staircase", 5.13, 1.73, 4.0, 2.0)  # wider than deep
    el = _stair_tread_elements(room)
    # indicator + treads + break line all run VERTICALLY for an E-W flight:
    for x1, y1, x2, y2 in [el["indicator"], *el["treads"], el["break_line"]]:
        assert x1 == x2 and y1 != y2
    assert el["arrow"][0] != el["arrow"][2]  # arrow advances along x
    assert el["arrow"][1] == el["arrow"][3]
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/karthik/projects/PlanForge/backend && .venv/bin/pytest tests/test_pdf_multi_floor_pages.py -k "stair" -v`
Expected: FAIL — `_stair_tread_elements` does not exist; FF label is "UP".

Guard step: `rg -n '"UP"' tests/` — confirm no existing test pins "UP" on the top-floor page.

**Step 3: Implement**

In `backend/app/engine/pdf.py` refactor `_draw_staircase_treads` to consume a pure geometry helper (metres in, metres out — drawing code only scales). The horizontal branch mirrors `plan_geometry.derive_stair` orientation (`plan_geometry.py:1548-1576`) exactly:

```python
def _stair_tread_elements(room) -> dict:
    """Orientation-aware stair geometry in metres (same heuristic as
    plan_geometry.derive_stair: depth >= width => flight climbs S->N,
    else W->E)."""
    inset = 0.115 / 2
    tread_depth_m = 0.27
    vertical_run = room.depth >= room.width
    if vertical_run:
        cross_lo, cross_hi = room.x + inset, room.x + room.width - inset
        num = max(3, min(16, int((room.depth * 0.5) / tread_depth_m)))
        step = (room.depth / 2) / (num + 1)
        treads = [(cross_lo, room.y + i * step, cross_hi, room.y + i * step) for i in range(1, num + 1)]
        return {
            "indicator": (cross_lo, room.y, cross_hi, room.y),
            "treads": treads,
            "break_line": (cross_lo, room.y + room.depth / 2, cross_hi, room.y + room.depth / 2),
            "arrow": (room.x + room.width / 2, room.y + room.depth * 0.58,
                      room.x + room.width / 2, room.y + room.depth * 0.80),
            "label_xy": (room.x + room.width / 2, room.y + room.depth * 0.80 + 0.12),
            "label_halign": "centre",
        }
    # E-W flight: indicator on the west (x-min) edge, treads stacked along x
    cross_lo, cross_hi = room.y + inset, room.y + room.depth - inset
    num = max(3, min(16, int((room.width * 0.5) / tread_depth_m)))
    step = (room.width / 2) / (num + 1)
    treads = [(room.x + i * step, cross_lo, room.x + i * step, cross_hi) for i in range(1, num + 1)]
    return {
        "indicator": (room.x, cross_lo, room.x, cross_hi),
        "treads": treads,
        "break_line": (room.x + room.width / 2, cross_lo, room.x + room.width / 2, cross_hi),
        "arrow": (room.x + room.width * 0.58, room.y + room.depth / 2,
                  room.x + room.width * 0.80, room.y + room.depth / 2),
        "label_xy": (room.x + room.width * 0.80 + 0.12, room.y + room.depth / 2),
        "label_halign": "left",
    }


def _draw_staircase_treads(c, rooms, scale, ox, oy, stair_label="UP"):
    """Draw staircase: floor-level indicator, tread lines, break line, arrow + label."""
    c.setDash()
    for room in rooms:
        if room.type != "staircase":
            continue
        el = _stair_tread_elements(room)
        rw = room.width * scale

        def _pts(seg):
            x1, y1, x2, y2 = seg
            return ox + x1 * scale, oy + y1 * scale, ox + x2 * scale, oy + y2 * scale

        c.setStrokeColor(HexColor("#000000"))
        c.setLineWidth(1.8)
        c.line(*_pts(el["indicator"]))

        c.setStrokeColor(HexColor("#333333"))
        c.setLineWidth(0.5)
        for t in el["treads"]:
            c.line(*_pts(t))

        c.setDash(4, 2)
        c.setStrokeColor(HexColor("#000000"))
        c.setLineWidth(0.75)
        c.line(*_pts(el["break_line"]))
        c.setDash()

        if rw >= 18:
            lbl_fs = max(8, min(12, rw * 0.30))
            tail = _pts((el["arrow"][0], el["arrow"][1], el["arrow"][2], el["arrow"][3]))
            tx, ty = tail[2], tail[3]
            c.setStrokeColor(HexColor("#000000"))
            c.setLineWidth(1.0)
            c.line(*tail)
            arrow_w = min(rw * 0.28, 7)
            p = c.beginPath()
            if room.depth >= room.width:
                p.moveTo(tx, ty + arrow_w); p.lineTo(tx - arrow_w / 2, ty); p.lineTo(tx + arrow_w / 2, ty)
            else:
                p.moveTo(tx + arrow_w, ty); p.lineTo(tx, ty - arrow_w / 2); p.lineTo(tx, ty + arrow_w / 2)
            p.close()
            c.setFillColor(HexColor("#000000"))
            c.drawPath(p, fill=1, stroke=0)
            lx, ly = ox + el["label_xy"][0] * scale, oy + el["label_xy"][1] * scale
            c.setFont("Helvetica-Bold", lbl_fs)
            if el["label_halign"] == "centre":
                c.drawCentredString(lx, ly + 2, stair_label)
            else:
                c.drawString(lx + 2, ly - lbl_fs / 2, stair_label)
```

At the call site (pdf.py:628, inside `_draw_floor_projected` — it receives both `floor_plan` and `layout`):

```python
        _floors = {fp.floor: fp for fp in (layout.basement_floor, layout.ground_floor,
                                           layout.first_floor, layout.second_floor) if fp}
        has_floor_above = any(f > floor_plan.floor and fp.rooms for f, fp in _floors.items())
        _draw_staircase_treads(c, rooms, scale, ox, oy,
                               stair_label="UP" if has_floor_above else "DN")
```

(If the actual function body at :628 is nested differently, adapt the variable names to what's in scope — `layout` and `floor_plan` are both parameters of `_draw_floor_projected`.)

**Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_pdf_multi_floor_pages.py tests/test_pdf_section_pages.py tests/test_pdf_page_composition.py -v`
Expected: PASS. Also visually inspect page 2 of a G+2 render (top floor shows "DN") via `render_page_png`.

**Step 5: Commit**

```bash
git add backend/app/engine/pdf.py backend/tests/test_pdf_multi_floor_pages.py
git commit -m "fix(engine): orientation-aware stair treads and floor-aware UP/DN label (#1, #5)"
```

---

## Task 6: Entrance-placement failures are diagnosed, not silent (#6, #6b, G, #6d epic)

**Files:**
- Modify: `backend/app/engine/cad_elements.py:116-136` (`FloorDrawing` + `to_dict`)
- Modify: `backend/app/engine/plan_geometry.py:701-745` (`_place_main_entrance`), `:748-773` (`derive_openings`), `:1587-1618` (`build_floor_drawing`)
- Test: `backend/tests/test_plan_openings.py`

**Step 1: Write the failing tests**

Append to `backend/tests/test_plan_openings.py`:

```python
def _drawing_for(rooms):
    from app.engine.models import FloorPlan
    from app.engine.plan_geometry import build_floor_drawing

    fp = FloorPlan(floor=0, floor_type="ground", rooms=rooms)
    return build_floor_drawing(fp, _cfg_9x15())


def test_main_door_all_parking_frontage_is_diagnosed():  # #6d
    drawing = _drawing_for([
        _room("porch", 1.23, 1.73, 4.0, 3.0, rtype="parking"),
        _room("stair", 5.23, 1.73, 2.0, 7.0, rtype="staircase"),
        _room("living", 1.23, 4.73, 4.0, 3.0),
    ])
    assert any(d.startswith("main_entrance:") for d in drawing.diagnostics)
    assert not any(o.is_main for o in drawing.openings)


def test_main_door_too_narrow_candidate_is_diagnosed():  # #6b
    # entry is the ONLY road-facing room; living sits behind it
    drawing = _drawing_for([
        _room("entry", 1.23, 1.73, 0.97, 3.0),  # < 1.05 + 2 jambs
        _room("living", 1.23, 4.73, 4.0, 4.0),
    ])
    diag = [d for d in drawing.diagnostics if d.startswith("main_entrance:")]
    assert diag and "too narrow" in diag[0]


def test_main_door_off_plate_front_is_diagnosed():  # #6
    drawing = _drawing_for([
        _room("living", 1.23, 2.5, 5.0, 5.0),  # 0.77m behind plate front 1.73
        _room("stair", 6.23, 1.73, 1.5, 6.0, rtype="staircase"),
    ])
    assert not any(o.is_main for o in drawing.openings)
    assert any(d.startswith("main_entrance:") for d in drawing.diagnostics)


def test_diagnostics_key_present_in_drawing_dict():
    drawing = _drawing_for([_room("a", 1.23, 1.73, 3.0, 3.0)])
    assert "diagnostics" in drawing.to_dict()
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/karthik/projects/PlanForge/backend && .venv/bin/pytest tests/test_plan_openings.py -k "diagnosed or diagnostics_key" -v`
Expected: FAIL — `FloorDrawing` has no `diagnostics` attribute.

**Step 3: Implement**

1. `cad_elements.py:128` — add the field (additive; `asdict` picks it up in `to_dict` automatically):

```python
    bounds: tuple[float, float, float, float]  # buildable bbox
    diagnostics: list[str] = field(default_factory=list)  # placement problems
```

2. `plan_geometry.py` — `_place_main_entrance` gains a `reasons` param and records per-room rejection causes (distinguishes #6 / #6b / G / #6d):

```python
def _place_main_entrance(
    rooms, obstacles, std, buildable, ewt, tol, reasons: list[str] | None = None,
) -> Opening | None:
    """... (keep existing docstring)"""
    bx1, by1, bx2, _by2 = buildable.bounds
    py1 = by1 + ewt
    coord = by1 + ewt / 2
    width = std.main_door_width_m
    gate_x = (bx1 + bx2) / 2
    cands = []
    rejected: list[str] = []
    for room in rooms:
        if abs(room.y - py1) > 2 * tol:
            continue  # not road-frontage — not a candidate at all
        if room.type in _NO_ENTRY_TYPES:
            rejected.append(f"{room.id}(type={room.type}) cannot host entry")
            continue
        lo, hi = room.x, room.x + room.width
        if hi - lo < width + 2 * _JAMB:
            rejected.append(
                f"{room.id} too narrow for main door "
                f"({hi - lo:.2f}m < {width + 2 * _JAMB:.2f}m)"
            )
            continue
        prio = _ENTRY_PRIORITY.get(room.type, 3)
        cands.append((prio, abs((lo + hi) / 2 - gate_x), room.id, room, lo, hi))
    for _prio, _dist, _rid, room, lo, hi in sorted(cands, key=lambda t: t[:3]):
        centre = _fit_along(
            gate_x, lo + _JAMB, hi - _JAMB, width, obstacles.for_wall(True, coord)
        )
        if centre is None:
            rejected.append(f"{_rid} fully blocked by columns/openings")
            continue
        door = _make_door(room, False, coord, centre, width, ewt, centre <= (lo + hi) / 2)
        door.is_main = True
        return door
    detail = "; ".join(rejected) if rejected else "no road-facing room at front plate"
    if reasons is not None:
        reasons.append(f"main_entrance: {detail}")
    logger.warning("no suitable road-facing room for a main entrance door: %s", detail)
    return None
```

IMPORTANT ORDERING NOTE: current code checks `_NO_ENTRY_TYPES` *before* the front-plate tolerance. Swap as shown (frontage first) so rejection reasons only mention genuinely road-facing rooms.

3. `derive_openings(..., floor: int = 0, reasons: list[str] | None = None)` — pass through:

```python
    if floor == 0:
        place(_place_main_entrance(rooms, obstacles, std, buildable, ewt, tol, reasons))
```

4. `build_floor_drawing` — collect and attach:

```python
    diagnostics: list[str] = []
    openings = derive_openings(
        rooms, walls, columns, get_opening_standards(), buildable,
        floor=floorplan.floor, reasons=diagnostics,
    )
    for d in diagnostics:
        logger.warning("floor %s: %s", floorplan.floor, d)
    ...
    return FloorDrawing(
        floor=floorplan.floor, walls=walls, openings=openings, columns=columns,
        junctions=junctions, dim_chains=derive_dim_chains(rooms, walls, cfg),
        labels=derive_labels(rooms, bounds=buildable.bounds),
        stair=derive_stair(rooms), bounds=buildable.bounds,
        diagnostics=diagnostics,
    )
```

This surfaces through layout persistence for free (`layout_store.py:219` stores `build_floor_drawing(...).to_dict()`), so future frontend work can read `drawing.diagnostics` — out of scope here. `render_pdf()`'s public contract (returns `bytes`) is unchanged.

**Step 4: Run tests**

Run: `cd /home/karthik/projects/PlanForge/backend && .venv/bin/pytest tests/test_plan_openings.py tests/test_plan_drawing.py tests/test_plan_geometry.py -v`, then full suite `.venv/bin/pytest -q`.
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/engine/cad_elements.py backend/app/engine/plan_geometry.py backend/tests/test_plan_openings.py
git commit -m "feat(engine): diagnose main-entrance placement failures on FloorDrawing (#6, #6b, G, #6d)"
```

---

## Task 7: Out-of-bounds room validation warning (#F)

**Files:**
- Modify: `backend/app/engine/plan_geometry.py:1587-1618` (`build_floor_drawing`)
- Modify: `backend/app/engine/models.py:84-85` (`PlotConfig` field comments)
- Test: `backend/tests/test_plan_openings.py` (or `test_plan_geometry.py` — match where Task 6 helpers landed)

**Step 1: Write the failing test**

```python
def test_rooms_outside_buildable_bounds_are_flagged():
    drawing = _drawing_for([
        _room("living", 1.23, 1.73, 4.0, 5.0),
        _room("stray", 12.0, 1.73, 3.0, 3.0),  # buildable max x is 8.0 for _cfg_9x15
    ])
    assert any(d.startswith("geometry:") for d in drawing.diagnostics)
```

(Compute the actual buildable bounds for `_cfg_9x15()` before fixing the coordinate — the point is `stray` lies wholly outside.)

**Step 2: Run to verify it fails**

Run: `cd /home/karthik/projects/PlanForge/backend && .venv/bin/pytest tests/test_plan_openings.py -k outside_buildable -v`
Expected: FAIL — no diagnostics produced today.

**Step 3: Implement**

In `build_floor_drawing`, right after `diagnostics: list[str] = []`:

```python
    bx1, by1, bx2, by2 = buildable.bounds
    oob = [
        r.id for r in rooms
        if r.x < bx1 - 0.05 or r.y < by1 - 0.05
        or r.x + r.width > bx2 + 0.05 or r.y + r.depth > by2 + 0.05
    ]
    if oob:
        diagnostics.append(
            "geometry: rooms outside buildable bounds: " + ", ".join(oob)
            + " (plot_width is the x-extent/frontage, plot_length the y-extent/depth — swapped?"
        )
```

In `models.py`, expand the field comments:

```python
    plot_length: float  # y-extent (front/road -> rear), metres. NOT the longer axis.
    plot_width: float  # x-extent (left -> right, road frontage), metres.
```

**Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_plan_openings.py -k outside_buildable -v` then full suite.
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/engine/plan_geometry.py backend/app/engine/models.py backend/tests/test_plan_openings.py
git commit -m "feat(engine): warn when rooms exceed buildable bounds (plot dimension mix-ups)"
```

---

## Task 8: New RoomTypes — `foyer`, `courtyard`, `wardrobe` (#C)

**Files:**
- Modify: `backend/app/engine/models.py:6-29` (RoomType Literal)
- Modify: `backend/app/engine/plan_geometry.py:65-77` (type-keyed tables), `:786`, `:1100`, `:1183`
- Modify: `backend/app/engine/pdf.py:163-175` (PALETTE), `:794-796` (`_draw_windows` habitable set)
- Test: `backend/tests/test_plan_openings.py`, `backend/tests/test_pdf_multi_floor_pages.py`

**Design decisions (behavioral mapping):**

| Type | Semantic mapping | Own door? | Entry host? | Windows? | Transit? |
|---|---|---|---|---|---|
| `foyer` | formal entry vestibule (was mapped to `passage`) | skipped like passage (neighbours open onto it) | YES — `_ENTRY_PRIORITY` 1 (after living, before passage) | yes (habitable) | circulation |
| `courtyard` | interior open-to-sky court (was mapped to `balcony`) | skipped (rooms open off it) | default (not in `_NO_ENTRY_TYPES`) | no | circulation |
| `wardrobe` | walk-in closet (was mapped to `store_room`) | default (gets a door, like store_room) | default | no | default |

**Step 1: Write failing tests**

Append to `backend/tests/test_plan_openings.py`:

```python
def test_foyer_hosts_main_entrance():
    openings, _ = _openings_for([
        _room("foyer", 1.23, 1.73, 2.5, 3.0, rtype="foyer"),
        _room("stair", 3.73, 1.73, 2.0, 3.0, rtype="staircase"),
        _room("living", 1.23, 4.73, 5.0, 4.0),
    ], _cfg_9x15())
    main = next((o for o in openings if o.is_main), None)
    assert main is not None
    assert main.swing_into_room_id == "foyer"


def test_courtyard_gets_no_own_door_but_is_reachable():
    rooms = [  # 3 rooms stacked around a central courtyard strip
        _room("living", 1.23, 1.73, 4.0, 3.0),
        _room("court", 1.23, 4.73, 4.0, 2.0, rtype="courtyard"),
        _room("stair", 1.23, 6.73, 4.0, 3.0, rtype="staircase"),
    ]
    openings, _ = _openings_for(rooms, _cfg_9x15())
    court_doors = [o for o in openings if o.kind == "door" and o.swing_into_room_id == "court"]
    assert court_doors == []
    doors = [o for o in openings if o.kind == "door"]
    assert doors  # neighbours still placed doors on the shared walls
```

Append to `backend/tests/test_pdf_multi_floor_pages.py`:

```python
def test_new_room_types_render():
    # non-overlapping tiling of the _cfg plate (x 1.13..10.33, y 1.73..13.23)
    gf = [
        _room("foyer", "foyer", 1.13, 1.73, 2.5, 3.0),
        _room("court", "courtyard", 3.63, 1.73, 1.5, 3.0),
        _room("stair", "staircase", 5.13, 1.73, 2.0, 5.0),
        _room("ww", "wardrobe", 7.13, 1.73, 2.0, 2.0),
        _room("bed", "bedroom", 7.13, 3.73, 2.5, 3.0),
        _room("living", "living", 1.13, 4.73, 4.0, 4.0),
    ]
    pdf = render_pdf("NewTypes", _make_layout(gf, ff_rooms=[]), _cfg(), 3)
    assert pdf_pages(pdf) == 6
```

**Step 2: Run to verify they fail**

Expected: foyer treated as unknown default (no `_ENTRY_PRIORITY` → may lose main-door eligibility ordering), courtyard gets its own door if one fits. The render smoke test passes even pre-schema-change (unknown types are only `Literal`-constrained, and the fill code uses `PALETTE.get(room.type, default)` at `pdf.py:420`, so no KeyError) — its purpose is regression-cover for the new types, not a red test.

**Step 3: Implement**

1. `models.py` — append to the Literal: `"foyer"  # entry vestibule`, `"courtyard"  # interior open-to-sky court`, `"wardrobe"  # walk-in closet`.
2. `plan_geometry.py`:
   - `_NO_DOOR_TYPES = _PARKING_TYPES | {"passage", "foyer", "courtyard"}` (extends Task 2's set).
   - `_ENTRY_PRIORITY = {"living": 0, "foyer": 1, "passage": 2, "dining": 3}`.
   - `_DOOR_NEIGHBOUR_PRIORITY = {"passage": 0, "foyer": 0, "courtyard": 1, "living": 1, "dining": 2, "staircase": 3}`.
   - `_CIRCULATION_TYPES = {"passage", "foyer", "courtyard", "living", "dining"}`.
   - Read lines ~1095-1105 and ~1178-1190 (navigability checks keyed on `"passage"`); mirror passage handling for foyer/courtyard wherever the code assumes "skipped own-door == needs special treatment in BFS". Verify by running the navigability tests (`tests/test_plan_openings.py` covers connectivity asserts).
3. `pdf.py` — add `foyer`, `courtyard`, `wardrobe` to `PALETTE` (white fill / black stroke like the rest); add `"foyer"` to the `habitable` set in `_draw_windows` (line 796).
4. Update the room-type doc comments in the spec-mapping table above — no `room_specs.json`, solver, or archetype changes (solver does not GENERATE these types; they arrive via hand-authored/editor data).

**Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_plan_openings.py tests/test_pdf_multi_floor_pages.py tests/test_solver.py -v`, then full suite.
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/engine/models.py backend/app/engine/plan_geometry.py backend/app/engine/pdf.py backend/tests/
git commit -m "feat(engine): add foyer, courtyard and wardrobe room types (#C)"
```

---

## Task 9 (OPTIONAL — confirm with user): Frontend labels/colors for the new RoomTypes

**Files:**
- Modify: `frontend/src/lib/layout-types.ts:216-230` (ROOM_TYPES), `frontend/src/lib/room-type-labels.ts:17,43`, `frontend/src/components/floor-plan-svg.tsx:47-88`, `frontend/src/components/plan-3d-scene.tsx:46-56`, `frontend/messages/{en,ta,hi}.json:~148`

**Verification gate BEFORE touching `layout-types.ts`:** adding to `ROOM_TYPES` makes the types selectable in the interactive editor → they can flow into `custom_room_config` → CP-SAT. Confirm the solver tolerates a `CustomRoomSpec` with an unknown-to-`room_specs.json` type (grep `custom_room_config` in `backend/app/engine/solver.py` and read the handling). If it crashes: add display labels/colors only, skip the dropdown entries.

Steps: mirror the existing `store_room`/`balcony` entries (labels + light/dark fill maps; foyer ≈ passage colors, courtyard ≈ balcony colors, wardrobe ≈ store_room colors); add i18n strings in all three locales; run frontend lint/typecheck (`bunx tsc --noEmit` / repo's `/cq` equivalent); commit as `feat(frontend): labels and colors for foyer/courtyard/wardrobe room types`.

---

## Task 10 (OPTIONAL — docs-side harness): J + dyadic snap refinement

**Files:**
- Modify: `docs/superpowers/specs/reverse_engr/_harness/reconstruct.py`

Only if the harness will be reused (per the spec's own note).

- Fold the dyadic-snap recipe (workaround #6, `q = 1024.0`) into the canonical room-builder helper next to the existing corner-pair recipe.
- Standardize `save_design_json()`: always emit BOTH `reconstructed_*_area_all_rooms_sqft` and `reconstructed_*_area_enclosed_only_sqft` (enclosed excludes `parking*`, `balcony`, `courtyard`, `garage`), fixing J going forward.
- Do NOT rewrite existing `re_data_*.json` files — they are dated historical records; add a one-line note in each new file's `notes` documenting the convention used.
- Test: re-run `check_connectivity()` over one existing design's room list built with the dyadic snap to confirm zero spurious DISCONNECTED reports.

---

## Task 11: Spec addendum + full verification

**Files:**
- Modify: `docs/superpowers/specs/solver_limitations.md`

**Step 1:** Append a short addendum section at the end of the doc:

```markdown
---

## Resolution status (2026-08-10)

| Item | Status | Fix |
|---|---|---|
| #1, #5 | Fixed | `_stair_tread_elements` orientation + UP/DN labels in `pdf.py` |
| #2 | Fixed | `_NO_DOOR_TYPES` in `plan_geometry.py` |
| #3, H | Fixed | `section_cut_line()` mid-line fallback |
| #6a | Fixed | `_ordered_floors()` in `render_pdf` |
| #6c | Fixed | `derive_walls()` room-union ring |
| #6, #6b, G, #6d | Surfaced | `FloorDrawing.diagnostics` (placement redesign for #6d still open) |
| F | Mitigated | out-of-bounds validation warning; rename deferred |
| C | Fixed | `foyer` / `courtyard` / `wardrobe` RoomTypes |
| #4, A, B, D, E | Out of scope | see plan `docs/plans/2026-08-10-solver-limitations-render-pipeline-fixes.md` |
```

Fill in actual commit SHAs if desired.

**Step 2: Full verification**

```bash
cd /home/karthik/projects/PlanForge/backend && .venv/bin/pytest -q
.venv/bin/ruff format app/engine tests && .venv/bin/ruff check app/engine tests
```

Expected: all green. (Ruff is the repo's Python quality gate per the python-pre-push skill; run from `backend/`.)

**Step 3: Commit**

```bash
git add docs/superpowers/specs/solver_limitations.md docs/plans/2026-08-10-solver-limitations-render-pipeline-fixes.md
git commit -m "docs: record resolution status of solver_limitations findings"
```

---

## Risk register (read before executing)

1. **Task 4 is the riskiest change** — `derive_walls` feeds every renderer (PDF, DXF, approval set, CCQS, section). Step 0/Step 4 baseline diff against the golden layout is mandatory. If solver layouts ever leave plate area uncovered, this changes their drawn walls — investigate before proceeding.
2. **Task 5** changes the top-floor stair label from "UP" to "DN" for every existing two-story layout — intended per #5, but it is a visible output change; flag it in the commit message and PR description.
3. **Task 3** changes page count/indices for G+2 and basement layouts — any downstream consumer hard-coding page indices (the spec called out a naive "page index 2" assumption in the reconstruction harness) must use title-text matching instead. `layout_store`/`render_runner`/`export.py` already iterate all four floors; verify no other page-index assumption exists (`rg -n "page.*index|\[2\]" backend/app/api/routes/export.py backend/app/services/`).
4. **Task 6** swaps the check order in `_place_main_entrance` (frontage before type-exclusion) — behavior-identical for placement, but re-verify `tests/test_plan_openings.py` passes unchanged.
5. **Task 8** foyer entry-priority change is safe for existing layouts (no existing type's relative order changes), but re-run the full openings suite.
