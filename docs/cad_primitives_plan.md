# Plan: Professional CAD Primitives for PlanForge DXF Export

## Context

The current DXF export produces basic drawings — continuous walls with door/window symbols
overlaid on top, no wall breaks at openings, no staircase treads, metre-only dimensions,
and a minimal title block.

The reference plan (Narayana Garden, Sivavela Builders) shows the professional Indian
construction drawing standard. This plan upgrades the DXF output to match it.

**Reference plan observations:**
- Walls have clean gaps (breaks) at every door/window/ventilator position
- Staircase: individual tread lines + direction arrow + diagonal cut line
- Dimensions: feet-inches chain (e.g. "39'-3"" overall, "35'" buildable inner)
- Ventilator symbols (V = 2'×2') for toilets/kitchens on exterior walls
- North arrow: 8-point star compass rose with N/S/E/W labels
- Title block: project title + per-floor buildup area in sqft + opening schedule legend

**Opening schedule (measurement legend) from reference:**
- MD = 3'6"×7'0" (Main Door)
- D  = 3'0"×7'0" (Door)
- D1 = 2'6"×7'0" (Bedroom Door)
- W  = 6'0"×4'0" (Window)
- W1 = 5'0"×4'0"
- W2 = 4'0"×4'0"
- KW = 4'0"×3'0" (Kitchen Window)
- V  = 2'0"×2'0" (Ventilator)

---

## Files to Create / Modify

| File | Action |
|------|--------|
| `backend/app/engine/cad_primitives.py` | **CREATE** — comprehensive CAD drawing library |
| `backend/app/api/routes/export.py` | **MODIFY** — `_render_dxf()` uses new primitives |
| `backend/tests/test_cad_primitives.py` | **CREATE** — unit tests |

`backend/app/engine/cad_elements.py` — kept intact, still used by PDF renderer.

---

## Part 1 — `cad_primitives.py` (new module, ~450 lines)

### 1.1 Unit Conversion Utility

```python
def metres_to_ftin(m: float) -> str:
    """Convert metres to feet-inches string. e.g. 3.048 → "10'-0\"""
    total_inches = m / 0.0254
    ft = int(total_inches // 12)
    inch = round(total_inches % 12)
    if inch == 12:
        ft += 1; inch = 0
    return f"{ft}'-{inch}\""
```

### 1.2 Opening Data Class

```python
@dataclass
class Opening:
    wall_key: tuple       # (round(x1,2), round(y1,2), round(x2,2), round(y2,2))
    t_start: float        # position along wall, normalised [0..1]
    t_end: float          # position along wall, normalised [0..1]
    kind: str             # "door" | "window" | "ventilator"
    width: float          # metres
    wall_length: float    # used to convert t back to absolute coords
```

### 1.3 `collect_openings()` — Opening Detection

```python
def collect_openings(
    rooms, ewt: float, iwt: float,
    bld_x: float, bld_y: float, bld_w: float, bld_d: float
) -> dict[tuple, list[Opening]]
```

**Algorithm:**

1. **Doors** — same adjacency detection as current `_render_dxf()`:
   - Vertical shared wall (`ra.x + ra.width ≈ rb.x`): door centred at midpoint of vertical overlap
   - Horizontal shared wall (`ra.y + ra.depth ≈ rb.y`): door centred at midpoint of horizontal overlap
   - Map door centre → which wall segment → compute `t_start` / `t_end`

2. **Windows** — same exterior detection as current `build_windows()`:
   - Habitable rooms (living, bedroom, kitchen, study, dining) touching building boundary
   - Window width = min(1.2, room.width × 0.6) on N/S walls, min(1.2, room.depth × 0.6) on E/W walls
   - Map to appropriate external wall segment

3. **Ventilators** — new:
   - Toilet, bathroom rooms touching exterior building boundary
   - V = 0.6 m wide on exterior face
   - Map to external wall segment

**Return:** `dict[wall_key → list[Opening]]` where each list is sorted by `t_start`.

### 1.4 `draw_wall_with_breaks()` — Double-line Wall with Opening Gaps

```python
def draw_wall_with_breaks(
    msp, wall: WallSegment, openings: list[Opening],
    layer: str, z: float
) -> None
```

**Algorithm:**

```
dx = wall.x2 - wall.x1
dy = wall.y2 - wall.y1
length = hypot(dx, dy)
px, py = -dy/length, dx/length   # perpendicular unit vector
h = wall.thickness / 2

# Build gap intervals from openings (in absolute units along wall)
gaps = [(op.t_start * length, op.t_end * length) for op in openings]
gaps.sort()

# Segments = wall minus gaps
segments = gap_subtract(0.0, length, gaps)

for (s_start, s_end) in segments:
    # Inner face line
    p1 = (wall.x1 + (s_start/length)*dx + h*px, wall.y1 + (s_start/length)*dy + h*py, z)
    p2 = (wall.x1 + (s_end/length)*dx + h*px, wall.y1 + (s_end/length)*dy + h*py, z)
    msp.add_line(p1, p2, dxfattribs={"layer": layer})

    # Outer face line
    p3 = (wall.x1 + (s_start/length)*dx - h*px, ...)
    p4 = (wall.x1 + (s_end/length)*dx - h*px, ...)
    msp.add_line(p3, p4, dxfattribs={"layer": layer})

    # HATCH fill only for solid segments
    hatch_corners = [p1_2d, p2_2d, p4_2d, p3_2d]
    add_hatch(msp, hatch_corners, "ANSI31" if wall.thickness >= ewt else "ANSI37", layer, z)
```

### 1.5 `draw_door()` — Door Leaf + Arc Swing

```python
def draw_door(
    msp, cx: float, cy: float, width: float,
    is_vertical_wall: bool, swing_left: bool,
    layer: str, z: float
) -> None
```

- **Door leaf**: LINE from hinge point, perpendicular into room, length = width
- **Swing arc**: quarter-circle ARC, centre = hinge, radius = width, angle = 90°
- Swing direction determined by `swing_left` flag (which room the door opens into)
- No wall lines — wall_with_breaks already left a gap

### 1.6 `draw_window()` — 3-line Symbol with Glazing Hatch

```python
def draw_window(
    msp, cx: float, cy: float, width: float,
    is_horizontal: bool, wall_thickness: float,
    layer: str, z: float
) -> None
```

- 3 parallel lines at offsets: `-wall_thickness/2`, `0`, `+wall_thickness/2`
- ANSI31 hatch (tiny scale 0.02) between the outer two lines — indicates glazing
- This improves on current 3-line approach by adding the glazing hatch

### 1.7 `draw_ventilator()` — High-level Louvred Opening

```python
def draw_ventilator(
    msp, cx: float, cy: float,
    is_horizontal: bool, layer: str, z: float
) -> None
```

- Default size: 0.6 m wide
- 4 closely-spaced parallel lines (louver indication), offset ±0.035 m
- Layer: `A-VENTILATOR` (magenta)

### 1.8 `draw_staircase()` — Treads + Arrow + Cut Line

```python
def draw_staircase(
    msp, room: Room, up_direction: str,   # "N" | "S" | "E" | "W"
    layer: str, z: float
) -> None
```

**Algorithm:**
```
# Determine stair run direction
if room.depth > room.width:
    # Stairs run N-S; treads are horizontal lines
    tread_count = int(room.depth / 0.25)
    for i in range(1, tread_count):
        y = room.y + i * (room.depth / tread_count)
        msp.add_line((room.x, y), (room.x + room.width, y))   # tread line
else:
    # Stairs run E-W; treads are vertical lines
    tread_count = int(room.width / 0.25)
    for i in range(1, tread_count):
        x = room.x + i * (room.width / tread_count)
        msp.add_line((x, room.y), (x, room.y + room.depth))

# Diagonal cut line (zig-zag at 60% of stair height)
mid_y = room.y + room.depth * 0.6
msp.add_lwpolyline([(room.x, mid_y), (room.x + room.width*0.4, mid_y + 0.15),
                    (room.x + room.width*0.6, mid_y - 0.15), (room.x + room.width, mid_y)])

# Direction arrow (pointing up)
arrow_x = room.x + room.width / 2
arrow_y_start = room.y + 0.15
arrow_y_end   = room.y + room.depth * 0.55
msp.add_line((arrow_x, arrow_y_start, z), (arrow_x, arrow_y_end, z))
# Arrowhead: small triangle at tip
msp.add_mtext("UP", insert=(arrow_x, arrow_y_end + 0.1), char_height=0.18)
```

### 1.9 `draw_dimension_chain()` — Feet-Inches Chain

```python
def draw_dimension_chain(
    msp,
    positions: list[float],   # sorted x (or y) coords of all room edges
    fixed_coord: float,        # y (for horiz chain) or x (for vert chain)
    offset: float,             # how far outside building to place dim line
    is_horizontal: bool,
    layer: str, z: float
) -> None
```

- `positions` = e.g. `[0.23, 2.63, 5.33, 7.83, 8.06]` (including wall faces)
- For each consecutive pair: `add_linear_dim(base, p1, p2, angle).render()`
- Dim text: `metres_to_ftin(p2 - p1)` — e.g. "7'-10\""
- Two dim chains per floor:
  - Bottom chain (horizontal): `y = bld_y - 1.5`
  - Right chain (vertical): `x = bld_x + bld_w + 1.5`
- Also add **overall** outer dimension 0.8 m further out than chain

### 1.10 `draw_north_arrow()` — 8-point Compass Rose

```python
def draw_north_arrow(
    msp, cx: float, cy: float,
    north_dir: str,   # "N" | "S" | "E" | "W"
    size: float,      # radius of compass, e.g. 0.8
    layer: str
) -> None
```

**Drawing:**
- 4 long spikes (cardinal): `(cx, cy)` → tip at `size` distance, each 15° wide at base
- 4 short spikes (diagonal NE/NW/SE/SW): `0.6 × size` length
- North spike: filled (solid hatch) — black
- Other spikes: outline only
- MTEXT "N", "S", "E", "W" at `size + 0.15` from centre

### 1.11 `draw_title_block()` — Bordered Block with Area + Legend

```python
def draw_title_block(
    msp,
    project_name: str,
    layout_id: str,
    gf_area_sqft: float,
    ff_area_sqft: float,
    plot_w: float, plot_l: float,
    insert_x: float, insert_y: float   # bottom-left of title block
) -> None
```

**Layout (mirrors reference plan):**
```
┌──────────────────────────────────────────────────────────────────┐
│        PROJECT TITLE — LAYOUT X (underlined, centred)            │
├──────────────────────────────────────────────────────────────────┤
│  GROUND FLOOR BUILDUP AREA       │  MEASUREMENTS:               │
│  = XXXX SQFT                     │  MD - (3'6"×7'0")            │
│                                  │  D  - (3'0"×7'0")            │
│  FIRST FLOOR BUILDUP AREA        │  W  - (6'0"×4'0")            │
│  = XXXX SQFT                     │  KW - (4'0"×3'0")            │
│                                  │  V  - (2'0"×2'0")            │
│  PlanForge  |  Generated by AI   │                              │
└──────────────────────────────────────────────────────────────────┘
```

- Outer border: thick LWPOLYLINE (lineweight 0.5)
- Title row: MTEXT, char_height=0.4, underlined
- Divider lines: internal LWPOLYLINE
- Area text: MTEXT, bold, char_height=0.25
- Measurements column: MTEXT, char_height=0.18
- Positioned at `y = bld_y - 5.0` (below the floor plan)

---

## Part 2 — Upgrade `_render_dxf()` in `export.py`

### 2.1 New Layers

```python
("A-STAIR",      colors.WHITE,   0.25),
("A-VENTILATOR", colors.MAGENTA, 0.18),
("A-TITLE",      colors.WHITE,   0.50),
```

### 2.2 New Drawing Flow (per floor)

```python
from app.engine.cad_primitives import (
    collect_openings, draw_wall_with_breaks,
    draw_door, draw_window, draw_ventilator,
    draw_staircase, draw_dimension_chain,
    metres_to_ftin,
)

# 1. Collect all openings (doors, windows, ventilators)
openings_map = collect_openings(rooms, ewt_m, iwt_m, bld_x, bld_y, bld_w, bld_d)

# 2. Draw walls with breaks
walls = build_walls_from_rooms(rooms, ewt_m, iwt_m, bld_x, bld_y, bld_w, bld_d)
for wall in walls:
    wall_key = (round(wall.x1,2), round(wall.y1,2), round(wall.x2,2), round(wall.y2,2))
    layer = "A-WALL-BRICK" if wall.thickness >= ewt_m else "A-WALL-INT"
    draw_wall_with_breaks(msp, wall, openings_map.get(wall_key, []), layer, z_offset)

# 3. Draw openings
for openings in openings_map.values():
    for op in openings:
        if op.kind == "door":        draw_door(msp, ...)
        elif op.kind == "window":    draw_window(msp, ...)
        elif op.kind == "ventilator": draw_ventilator(msp, ...)

# 4. Staircase
for room in rooms:
    if room.type == "staircase":
        draw_staircase(msp, room, up_direction=cfg.road_side, layer="A-STAIR", z=z_offset)

# 5. Room labels (upgraded to ft-in format)
for room in rooms:
    label = f"{room.name}\\P{metres_to_ftin(room.width)} × {metres_to_ftin(room.depth)}"
    msp.add_mtext(label, dxfattribs={"layer": "TEXT", "char_height": 0.2,
                                      "insert": (cx, cy, z_offset), "attachment_point": 5})

# 6. Columns (unchanged)

# 7. Dimension chains (replaces single add_linear_dim calls)
xs = sorted({round(r.x,3) for r in rooms} | {round(r.x+r.width,3) for r in rooms})
ys = sorted({round(r.y,3) for r in rooms} | {round(r.y+r.depth,3) for r in rooms})
draw_dimension_chain(msp, xs, fixed_coord=bld_y, offset=-1.5, is_horizontal=True, ...)
draw_dimension_chain(msp, ys, fixed_coord=bld_x+bld_w, offset=1.5, is_horizontal=False, ...)
```

### 2.3 North Arrow and Title Block (once, outside floor loop)

```python
# North arrow — top-right of drawing
draw_north_arrow(msp, cx=max_x + 2.5, cy=max_y - 1.5,
                 north_dir=cfg.north_direction, size=0.8, layer="TEXT")

# Title block — below drawing
gf_sqft = sum(r.area for r in layout.ground_floor.rooms) * 10.764
ff_sqft = sum(r.area for r in layout.first_floor.rooms) * 10.764
draw_title_block(msp, project_name, layout.id,
                 gf_sqft, ff_sqft, cfg.plot_width, cfg.plot_length,
                 insert_x=min_x, insert_y=min_y - 5.5)
```

---

## Part 3 — Tests (`test_cad_primitives.py`)

```python
def test_metres_to_ftin_whole_feet():
    assert metres_to_ftin(3.048) == "10'-0\""

def test_metres_to_ftin_with_inches():
    assert metres_to_ftin(1.067) == "3'-6\""

def test_metres_to_ftin_zero():
    assert metres_to_ftin(0.0) == "0'-0\""

def test_collect_openings_finds_door_on_shared_wall():
    # Two adjacent rooms → door detected on shared wall

def test_collect_openings_finds_window_on_exterior():
    # Habitable room touching bld_y → window on front wall

def test_collect_openings_ventilator_for_toilet():
    # Toilet touching exterior → ventilator added

def test_opening_gaps_are_sorted_and_non_overlapping():
    # Multiple openings on same wall → gaps don't overlap

def test_wall_key_round_trip():
    # wall_key from WallSegment matches key used in openings_map
```

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Parameterise walls as t∈[0,1] | Works for any wall orientation (H or V), easy to compute gap intervals |
| Opening collection separate from drawing | Allows wall drawing to know all gaps before it starts any lines |
| `cad_elements.py` kept intact | PDF renderer still uses it; no regression |
| Feet-inches in dim text | Indian construction standard — matches reference plan exactly |
| Title block at y = bld_y − 5.5 | Matches reference plan layout (title block below the drawing) |
| `metres_to_ftin` rounds inches | Avoids "3'-5.7\\"" — construction drawings use whole inches |

---

## Verification Steps

1. `cd backend && uv run pytest tests/test_cad_primitives.py -v` — new tests pass
2. `cd backend && uv run pytest` — all 55 existing tests still pass
3. Start backend + generate a project via API, export DXF
4. Open DXF in LibreCAD / ezdxf viewer and verify:
   - [ ] Walls have clean gaps at all door positions
   - [ ] Walls have clean gaps at all window positions
   - [ ] Toilet/kitchen walls have ventilator gaps
   - [ ] Staircase room shows tread lines + UP arrow + cut line
   - [ ] Bottom dim chain shows individual room widths in feet-inches
   - [ ] Right dim chain shows individual room depths in feet-inches
   - [ ] North arrow (star) visible top-right
   - [ ] Title block shows GF/FF sqft areas and opening schedule
   - [ ] Room labels show "Name\nW × D" in feet-inches
