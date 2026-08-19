# Known issues flagged during the solver-capability-uplift branch

Raised 2026-08-19 on branch `feat/solver-capability-uplift`. All three are
**pre-existing** — none was introduced by that branch, and none is fixed by it.
Each was found while verifying something else, confirmed by measurement, and
deliberately left alone because fixing it was outside the approved scope.

Ordered by user impact.

---

## 1. The compound-wall gate and the front door sit on different edges

**Severity: high — self-contradictory drawings on 3 of 4 orientations.**

`road_side` is read two incompatible ways in the same engine:

- `plan_geometry._place_main_entrance` treats it as a **compass direction**. The
  road-facing edge is always y-min ("the road is always the y-min edge
  (archetypes/vastu convention)"), and `road_side` names which compass direction
  that edge faces.
- `geometry._compound_wall_sides` treats it as a **plot-local edge id**:
  y-min = "S", x-max = "E", y-max = "N", x-min = "W".

The two agree only when `road_side == "S"`. For an east road the compound-wall
gate is placed on the x-max edge while the main entrance door is placed on the
y-min edge — **the gate and the front door are on different sides of the house**.
Same for N and W.

`_place_main_entrance` also aligns the door to `gate_x`, the buildable midpoint
in x, whose entire purpose is to line the door up with the compound-wall gate
("cad_advanced centres the gate on the road side"). That alignment is meaningless
whenever the two edges disagree.

**Where:** `backend/app/engine/geometry.py:385-419`,
`backend/app/engine/plan_geometry.py:1473+`.

**Fix direction:** pick one meaning and make it the only one. The compass reading
is the one the Vastu engine, the PDF's `ROAD (EAST)` strip label, and the
frontend's "Road faces {road_side}" all already use, so `_compound_wall_sides` is
the odd one out. Changing it will move the gate on N/E/W plots, so it needs a
visual check, not just a green suite.

**Why no test caught it:** the two readings live in different modules and no test
asserts that the gate edge and the entrance edge are the same edge. That
assertion is the regression test to write first.

---

## 2. Every north arrow in the product is wrong

**Severity: high — corrected upward after a closer look. There are THREE arrow
drawers and none of them is right, including on the default south plot.**

| drawer | orientation input | behaviour |
|---|---|---|
| `approval_pdf._draw_large_north_arrow` | takes `road_side` | **never references it**; always drawn straight up |
| `pdf._draw_north_arrow` | takes none at all | always drawn straight up |
| `cad_primitives.draw_north_arrow` | takes `north_dir` and does use it | fed `north_dir = cfg.road_side` by the DXF export |

The plan is drawn road-at-bottom (y-min), so the sheet's up direction is
geographic north **only** when `road_side == "S"`. The two ReportLab drawers are
therefore correct for a south plot and 90 or 180 degrees wrong otherwise.

The DXF one is worse. `export.py` passes `north_dir = getattr(cfg, "road_side", "S")`,
and `draw_north_arrow` maps `{"N": 90, "E": 0, "S": 270, "W": 180}` degrees. So a
south-facing plot -- the default -- gets its filled north spike drawn at 270
degrees, pointing **down the sheet, at the road**, when true north is up. It is
180 degrees wrong on the most common configuration, and wrong differently on the
other three. The arrow points at the road on every plot.

**Where:** `approval_pdf.py` `_draw_large_north_arrow` (called twice);
`pdf.py` `_draw_north_arrow` (called at two sheets, plus `structural_sheet.py`);
`cad_primitives.py` `draw_north_arrow`, fed from `api/routes/export.py`.

**Fix direction:** one orientation source for all three.
`vastu.resolve_north_angle(cfg)` already returns the clockwise angle from the
plan's +y to true north, honouring a surveyed `north_angle_deg` over the road
side, and works for non-cardinal bearings. Rotate each glyph by it. The DXF
drawer additionally needs its caller to stop passing `road_side` as if it were a
north direction.

**Note:** `ROAD_SIDE_NORTH_ANGLE_DEG` was itself wrong for E and W until commit
`e11e500` on this branch, so any earlier attempt to fix the arrows from that
table would have inherited the error.

**Why no test caught it:** nothing asserts anything about arrow direction; the
PDF/DXF tests check that an arrow is emitted, not where it points.

## 3. A west-facing entrance has no auspicious cell

**Severity: low — a missing preference, not a wrong output.**

The main entrance can only sit on the road-facing (y-min) wall, so its candidates
occupy exactly one row of the 3x3 Vastu grid. After `e11e500` (E/W grids
unswapped) and `320e376` (south preference added), the rows are:

| road_side | front row | auspicious set | tie-break |
|---|---|---|---|
| S | `[SW, S, SE]` | `("SE",)` | fires |
| N | `[NE, N, NW]` | `("N","NE","E")` | fires |
| E | `[SE, E, NE]` | `("N","NE","E")` | fires |
| W | `[NW, W, SW]` | `("N","NE","E")` | **cannot fire** |

**West is the only orientation with no sanctioned cell in its front row**, so
enabling Vastu changes nothing about where a west-facing entrance is placed.

Classical practice would suggest preferring the **NW** end of a west-facing wall,
which would mirror the approved south/SE rule. That was **not** sanctioned by the
product owner (who approved SE for south only), so it was deliberately not
invented. This is a decision waiting on a person, not a defect.

**Fix direction if approved:** one entry in
`plan_geometry.ENTRANCE_AUSPICIOUS_ZONES_BY_ROAD_SIDE` — `"W": ("NW",)` — plus a
firing test mirroring `test_tie_break_fires_on_a_south_road`, and dropping `"W"`
from `test_tie_break_is_inert_on_a_west_road`. The machinery already exists.

**Caution for whoever does it:** `gate_x` is the buildable midpoint, so with
symmetric setbacks the middle candidate wins the distance key outright and the
Vastu key never decides anything. A fixture built without asymmetric setbacks
will pass while proving nothing — this has already cost one round on this branch.
