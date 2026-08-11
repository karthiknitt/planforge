# Rendering/Schema Limitations — Architectural Plan Pages (1-2)

**Date:** 2026-08-09
**Scope:** Findings from manually reverse-engineering two external reference
floor plans (`docs/superpowers/plans/cntmp01-gf-plan.webp` and Tata Steel
Aashiyana's Chettinad-07) into hand-authored `Room`/`FloorPlan`/`PlotConfig`
data, then rendering with the real `render_pdf()` pipeline — no solver
involved. Covers only the architectural pages (1-2 of the 6-page PDF:
ground floor + first floor plans). Structural (3-4), section, and elevation
pages (5-6) are explicitly out of scope here — revisit separately.

Each reconstruction is committed as a worked example under
`docs/superpowers/plans/` for reference.

---

## Confirmed codebase bugs / gaps

These are real issues in `backend/app/engine/`, not artifacts of the
reconstruction process — reproducible independently of any hand-authored
data.

### 1. Staircase treads only support a south→north ascent

`backend/app/engine/pdf.py:732` (`_draw_staircase_treads`) always draws the
"first tread" (floor-level indicator) at `room.y` (the room's south/front
edge) and climbs toward `room.y + depth` (north). Tread lines are always
horizontal segments spanning `room.width`, stacked along `depth`. There is
no width-vs-depth check and no rotation flag on `Room` — an east-west
running flight cannot be rendered correctly today, regardless of how the
room rectangle is placed or sized.

**Impact:** any reference plan whose staircase actually runs east-west will
always render with the wrong tread orientation. Not fixable by room
placement alone.

### 2. Parking rooms have no protection from getting an interior door

The per-room door-assignment loop in `derive_openings()`
(`backend/app/engine/plan_geometry.py:785-786`):

```python
for idx, room in sorted(enumerate(rooms), key=lambda t: t[1].id):
    if room.type == "passage":
        continue
```

only skips rooms typed `"passage"`. `_NO_ENTRY_TYPES`
(`plan_geometry.py:67`, `_WET_TYPES | {"parking", "staircase"}`) is consulted
*only* when selecting which room hosts the **main** entrance — it plays no
role in this loop. So even a room typed exactly `"parking"` (the literal
string that IS in that exclusion set) still gets an interior door assigned
if it touches any neighboring room.

**Impact:** any car porch / parking room that shares a wall with an interior
room (living room, entry, etc.) gets a spurious interior door drawn into an
outdoor space. There is currently no way to mark a room "outdoor / doesn't
need a door" except keeping it physically detached (a real gap) from every
neighbor — the workaround used in both reconstructions here, not a proper
fix.

### 3. `section_cut_line()` crashes uncaught if a floor has no staircase

`backend/app/engine/section_geometry.py:25`:

```python
stair = next(r for r in rooms if r.type == "staircase")
```

A bare `StopIteration`, uncaught anywhere up the call chain
(`render_pdf()` → `_draw_floor_projected()` → `section_cut_line()`). Hit
directly during the first reconstruction (`cntmp01`) when its placeholder
first floor was given an empty room list.

**Impact:** a floor legitimately having no further stairs (e.g. a
terrace-only top floor on a G+2) is a plausible real data state, and it
currently takes down the entire `render_pdf()` call with an unhelpful trace
instead of a clear error or a graceful no-section-cut fallback.

### 4. No connectivity check on a floor's room graph

`plan_geometry.py` has no connected-components / graph-validity check
anywhere (confirmed via grep — zero matches for anything resembling one).
The exterior wall is a raw Shapely `union()` of room rectangles
(`wall_polygons()`), so if that union isn't a single connected shape, the
renderer silently draws whatever results rather than raising or warning.

GCS's `_phantom_wall_count` (`backend/app/quality/ccqs.py:185`) catches a
wall bisecting a room's interior, but there's no equivalent "is this floor's
room graph one connected component" check.

**Impact:** a data-entry mistake that leaves two clusters of rooms
disconnected (as nearly happened while reconstructing Chettinad-07's first
floor, before a fix) would silently produce a broken or nonsensical wall
outline rather than a clear error. Worth considering as a candidate
additional GCS component — flagged here for the layout quality critique
loop (see
`docs/superpowers/specs/2026-08-09-layout-quality-critique-loop-design.md`),
not fixed as part of this pass.

### 5. Stair label is always "UP", never floor-aware

Same function as #1. Even on a floor with nothing above it, the stair room
still draws an "UP" arrow pointing at nothing above the top floor. Minor,
but a real gap in floor-awareness — the renderer has no concept of "this is
the top floor" when labeling a stair.

### 6a. `render_pdf()` silently drops the second floor (and basement) entirely — HIGH SEVERITY, likely production-impacting

**Found while reconstructing Modern-09 (a real G+2 design), not an artifact
of hand-authored data.** `backend/app/engine/pdf.py:275` and `:290` — both
the architectural-page loop and the structural-page loop are hard-coded to:

```python
for floor_plan in [layout.ground_floor, layout.first_floor]:
```

`grep` confirms zero references to `second_floor` or `basement_floor`
anywhere in `pdf.py`. `Layout.second_floor` and `Layout.basement_floor`
(`models.py:70-77`) are real, populated fields — `PlotConfig` supports
G+2/G+3/basement configurations elsewhere in the product (see the Stage-2
structural PRD) — but `render_pdf()` always emits exactly 6 pages
(GF-arch, FF-arch, GF-structural, FF-structural, section, elevation)
regardless of how many floors the building actually has. A G+2 building's
second floor is completely absent from both its architectural and
structural pages — not degraded, not warned about, just missing, with the
PDF looking like a complete, valid G+1 document.

Confirmed by rendering Modern-09 (G+2): `render_and_save()`'s naive
"page index 2 = second floor" assumption grabbed page index 2, which
turned out to be **"Ground Floor — Beam/Column Layout"** (the structural
page), not an SF architectural page — because there isn't one.

**Contrast:** `derive_section()` (`section_geometry.py:290-292`) and (by
extension) the elevation view *do* already handle `second_floor` correctly
(`floors = [layout.ground_floor, layout.first_floor]; if
layout.second_floor is not None: floors.append(...)`) — so the section/
elevation pages are fine. Only the two per-floor page-emission loops in
`render_pdf()` itself were never updated when third-floor support was
added elsewhere in the codebase. This is a straightforward, contained fix
(loop over `[layout.basement_floor, layout.ground_floor, layout.first_floor,
layout.second_floor]` filtering `None`s, same pattern already used in
`derive_section`) — flagging for a real fix, not just a workaround, since
it silently affects every G+2+ PDF the product generates today.

### 6. Main entrance placement fails silently

`_place_main_entrance()` (`plan_geometry.py:700`) requires a road-facing
room's front edge to sit within `2 * tol` of the front plate boundary
(`setback + EWT`, i.e. `setback + 0.23m`) — not just the raw setback line.
Missing that boundary by even the wall-thickness offset produces only a
`logger.warning("no suitable road-facing room for a main entrance door")`,
never an exception or a field on the returned result.

The tight tolerance itself is defensible (a visibly mispositioned door is
worse than none), but the silent failure mode is not — a full `render_pdf()`
call can complete "successfully" with zero marked entrance and nothing in
the return value flags that. Hit on both reconstructions' first pass.

### 6b. A road-facing candidate narrower than the door itself is silently skipped — a THIRD distinct main-door failure trigger

Found on Assamese-15 (OCR-pipeline validation run, 2026-08-10), distinct from
both #6 (tolerance miss) and G (columns blocking an eligible room).
`plan_geometry.py:729`:

```python
if hi - lo < width + 2 * _JAMB:
    continue
```

A road-facing candidate room is rejected outright — before either the #6
tolerance check or G's column-avoidance check even run — if it is narrower
than `main_door_width_m` (1.05 m) plus two door jambs. On Assamese-15 the
only non-`parking` room touching `front_y()` was a 3'2" (0.97 m) entry
passage, just under that threshold. Narrow entry passages/foyers around 1.0 m
wide are common in compact Indian house plans, so this is not an edge case.
Same silent-failure shape as #6 and G (a logged warning, `render_pdf()`
returns "success", nothing on the return value) — worth tracking alongside
them as a third root cause of the same visible symptom (no MD row in the
opening schedule) if the return value is ever extended to surface this.

### 6c. A floor's exterior wall ring is drawn from the plot's buildable bounds, not the floor's own room union — leaves a false wall around empty space

First observed in Modern-01's reconstruction notes (2026-08-09) but never
promoted into this numbered list; independently re-confirmed on Assamese-07's
first floor (OCR-pipeline validation run, 2026-08-10). `derive_walls()`
builds a floor's external wall ring from `buildable_polygon(cfg)` — the
*plot's* setback-derived bounding box — rather than from the actual union of
that floor's own rooms. On a floor whose footprint doesn't fill the full
buildable envelope (e.g. Assamese-07's first floor, which leaves a roof void
over part of the ground-floor footprint), the renderer still draws a full
wall ring around the *entire* buildable rectangle, including the empty area
with no rooms in it — a false wall enclosing nothing. Not a crash, not a
silent failure like #6/#6b — a visibly wrong wall on the rendered page. Worth
a real fix (`derive_walls()` should union the floor's actual rooms, falling
back to the buildable bounds only when a floor is intentionally full-footprint).

---

## Hard schema limits (not bugs — inherent design choices, not worth "fixing")

### A. `Room` is rectangle-only

`backend/app/engine/models.py:33` — `Room` has only `x, y, width, depth`
(axis-aligned rectangle). No polygon support, no L-shapes, no notches.

**Impact on reconstruction fidelity:** any reference-plan room that isn't a
clean rectangle has to be dropped or approximated. Both reconstructions
dropped at least one small non-rectangular or dimension-less nook (Mandir on
`cntmp01`'s ground floor; Terrace on Chettinad-07's first floor) rather than
force them into a box that would overlap a neighbor. This is a deliberate,
accepted tradeoff of the schema (matches the Lane B convention in the
critique-loop design spec) — not something to change.

### B. `PlotConfig` fields are solver-input-shaped, not all render-consumed

Several `PlotConfig` fields (e.g. `attached_toilets`, `has_pooja`,
`custom_room_config`) exist to steer the CP-SAT solver's room generation and
have no effect when `render_pdf()` is called directly on a hand-authored
`Room` list (as both reconstructions did, bypassing the solver entirely).
Not a bug — just a scope note for anyone reusing this reconstruction
approach: only `plot_length`, `plot_width`, the four `setback_*` fields,
`road_side`, and a handful of others actually influence the rendered output
in this bypass-the-solver path.

---

## Reconstruction workarounds that compensate for the above

Documented here so the eventual harness (see conversation — build only on
explicit go-ahead) encodes these as a checklist rather than rediscovering
them per plan:

1. Every adjacent room pair must share an **exact** touching coordinate on
   the shared edge (not "close enough") — works around #4 (no connectivity
   validation means a stagger silently produces a broken exterior wall
   instead of an error).
2. Road-facing entry rooms must start at `setback + 0.23` (EWT), not the raw
   setback value — works around #6's silent main-door failure.
3. Parking/car-porch rooms need a real physical gap (not just a different
   `RoomType` string) from every neighboring room — works around #2.
4. Every floor, including placeholder/unused ones, needs at least one
   `staircase`-typed room — works around #3.
5. Floor-to-floor identical room dimensions in the source material (a
   bedroom or toilet that's the same size on both floors) are a free
   structural cross-check that a reconstruction's column grid is consistent
   — not a workaround, but a validation signal worth actively looking for.
6. Rounding coordinates for a shared edge is NOT safe just because both rooms
   are built from "the same grid" — it must be done on the **corners**, not
   on the origin+extent independently, or edges drift by IEEE-754 rounding
   error and `check_connectivity()` reports a false `DISCONNECTED` with no
   hint that it's a rounding artifact rather than a misread adjacency. Found
   and progressively sharpened across three independent redo batches on the
   Modern-category run (2026-08-10):
   - Naive: `x=round(x1*FTM,4), width=round((x2-x1)*FTM,4)` — fails because
     `round(x1)+round(x2-x1) != round(x2)` by up to 1e-4 m.
   - Better: round both corners, take width as the *difference of the
     already-rounded* corners (`ax,bx = round(x1*FTM,4), round(x2*FTM,4);
     width = bx-ax`) — still not fully safe, because `x + width` is computed
     independently downstream (by `check_connectivity()` / Shapely) and can
     land ~1 ULP away from the neighbouring room's stored `x`, since not
     every rounded decimal is an exact binary fraction.
   - Robust: snap corners to a **dyadic grid** (a power-of-two denominator,
     e.g. `q = 1024.0; round(x1*FTM*q)/q`) before taking the difference.
     Multiples of `2**-10` are exactly representable in `float64`, so
     `x + width == x_of_next_room` holds bit-for-bit, not just "close
     enough". This is the only version confirmed to survive a full 18-design
     batch with zero spurious `DISCONNECTED` reports.
   This is a sharper, code-level version of workaround #1 above and belongs
   in the harness's canonical room-builder helper (`_harness/reconstruct.py`
   already carries the corner-pair recipe; the dyadic-snap refinement is
   worth folding in too if the harness is reused again).

---

## Bulk-reconstruction findings (Modern category harness run, 2026-08-09)

Findings from running the reusable harness
(`docs/superpowers/specs/reverse_engr/_harness/`) against Tata Steel
Aashiyana's "Modern" style category (26 designs probed, 18 with usable plan
images). Scope: single-pass, best-effort reconstruction per design,
documenting hurdles rather than iterating to perfection (explicit
instruction).

### C. No RoomType for foyer, interior courtyard/light-well, or wardrobe/closet

`RoomType` (`backend/app/engine/models.py:6`) has no entries for three room
kinds that are extremely common in this reference set:

- **Foyer / entry vestibule** — mapped to `"passage"` (closest circulation
  analog; loses the "this is a formal foyer, not a corridor" semantic).
- **Interior landscape court / light-well** (open-to-sky, but fully enclosed
  by the building footprint, unlike a `balcony` which is edge-attached) —
  mapped to `"balcony"` (closest open-air analog available).
- **Walk-in wardrobe (W.Ward)** — mapped to `"store_room"` (closest small
  enclosed-storage analog).

None of these are wrong renders, but all three are lossy relabelings, and
`"balcony"` in particular carries edge-of-building placement assumptions
(natural-light/exterior-facing scoring in the layout scorer) that don't
really apply to an interior courtyard. Worth adding real `RoomType` entries
if this reference set is used for anything beyond one-off PDF generation.

### D. Straightening jogged source layouts into rectilinear columns inflates area

Every design probed in this category has room boundaries that jog/offset
rather than aligning to a clean shared grid (e.g. a bedroom block that's
wider than the wet-room strip beneath it, single-room "notches" like a
landscape court breaking what would otherwise be a straight column edge).
Since `Room` is rectangle-only (limitation A) and the harness's
`check_connectivity()` requires a single connected component with no
overlaps, the practical reconstruction pattern that reliably renders clean
on the first pass is a **3-column "spine" layout**: two side stacks of
rooms, each full-width within its column, plus a full-depth central
corridor/staircase column touching both — with the shorter stack's last
room padded to match the taller stack's total depth.

**Impact:** this reliably produces a connected, valid, main-door-eligible
floor, but at the cost of area fidelity — Modern-01's reconstructed ground
floor came out ~22% larger than the source's declared area (1874 vs 1532
sqft) purely from straightening jogs into full rectangles and padding short
columns. This is an accepted tradeoff for single-pass reconstruction, not a
bug — but it means declared vs. reconstructed area should never be treated
as a fidelity signal beyond "same order of magnitude."

### F. `PlotConfig.plot_width`/`plot_length` naming is inverted from intuition

`app/engine/geometry.py:34-35,99` — despite the names, `plot_width` is the
**x-extent** (road-facing frontage) and `plot_length` is the **y-extent**
(front-to-rear depth): `box(0, 0, cfg.plot_width, cfg.plot_length)`. This
reads backwards in natural English ("length" usually implies the longer/
horizontal dimension, "width" the shorter) and caused a real, *silent* bug
on the first two harness reconstructions — both had the fields swapped for
several iterations. The danger: nothing in `render_pdf()` validates room
coordinates against `buildable_polygon(cfg)` bounds, so a swapped
length/width renders with no error at all; only the dimension labels and
setback-margin lines in the output PDF are wrong (rooms may even overflow
the drawn compound boundary without any visual glitch flagging it). Worth a
field rename (`plot_frontage_m` / `plot_depth_m`) or, short of that, a
validation warning when room extents exceed `buildable_polygon(cfg).bounds`.

### G. Auto-derived structural columns can block ALL main-door candidates, silently

`derive_columns()` (used internally by `build_floor_drawing()`) generates
structural column obstacles from the wall/room layout *before*
`derive_openings()` places the main door. `_place_main_entrance()`
(limitation #6 above) already fails silently on a coordinate-tolerance
miss; this is a distinct failure mode of the *same* silent-failure
function — confirmed on Modern-02 by isolating the call: passing an empty
`_ObstacleIndex([])` finds a valid main-door position into the
kitchen/dining room on the very first try, but the real pipeline (which
passes the 21 auto-derived columns for this floor) returns `None` for
*every* road-facing candidate room, not just one. A plan with several
road-facing rooms along the front wall (kitchen, car porch, foyer, etc. all
touching the front plate boundary) is more exposed to this than a plan with
a single obvious entry room, since `_fit_along`'s column-avoidance check
runs independently per candidate and columns are typically spaced at
regular structural-grid intervals across the *entire* front wall.

**Impact:** same as #6 (a "successful" `render_pdf()` call with a
door-schedule silently missing its MD row), but with a different and much
harder-to-predict trigger — it depends on where the solver-independent
column grid happens to land relative to every candidate room's door-fit
window, not just the position of one intended entry room.

### H. Genuinely stair-less single-story homes can't be reconstructed without inventing a stair

Modern-06 has no staircase at all in the source image (no "UP" arrow, single
story, `"Floors": "Ground Floor Only"`). Bug #3 (`section_cut_line()`
crashing on a stair-less room list) forces every reconstruction to insert at
least one `staircase`-typed room regardless of whether the source plan has
one — there is no way to render a true single-story home through this
pipeline without fabricating stairs that don't exist in reality. A real fix
would make the section-cut fall back to a plain vertical mid-line when no
staircase room exists, rather than crashing.

### E. Two-toilet-on-ground-floor plans are common but easy to mis-scope

Several Modern designs place a full ensuite bedroom (with its own toilet
*and* wardrobe) on the ground floor alongside a separate common toilet
serving the living/dining zone — i.e. two toilets and one bedroom on GF,
with the remaining bedrooms upstairs. Metadata's `"Type": "3 BHK"` count
covers all floors combined, not per-floor, so per-floor room lists must be
derived from the plan image itself, not inferred from the BHK count.

### I. A road-frontage floor whose only room is typed `"parking"` can NEVER get a main door

Found on Modern-26, a real, common "upside-down" duplex typology: all
bedrooms on the ground floor, all living/kitchen/dining upstairs, with the
entire ground-floor road frontage occupied by the car porch and the real
entrance being an external stair straight to the first floor. `RoomType`
`"parking"` is a member of `_NO_ENTRY_TYPES` (`plan_geometry.py:67`), so
`_place_main_entrance()` never considers it as a main-door candidate — by
design, correctly, taken alone. But combined with limitation #6 (silent
warning-only failure, no field on the return value), the result is a
ground-floor PDF page with **no marked entrance at all** and nothing in the
API response to say so. `render_pdf()` logs `"no suitable road-facing room
for a main entrance door"` four times for this design and returns "success."

This is distinct from #6 (tolerance miss), G (columns blocking an
otherwise-eligible room), #6b (a candidate too narrow to host the door), and
#6c (false wall ring) — here there is no eligible room on the frontage at
all, structurally, for the entire "porch-fronted upside-down house"
typology. Worth tracking as **#6d** if `render_pdf()`'s return value is ever
extended to surface entrance-placement failures — a plan of this typology
should probably place the door on the stair landing or flag "entrance not on
ground floor" rather than silently omitting it. Not fixed here, per the
"document, don't chase every renderer quirk" instruction for this pass.

(This numbering — #6, #6a–#6d, G — now covers five independently-discovered
root causes converging on the same visible symptom: a "successful"
`render_pdf()` call with no marked main entrance. Worth treating as one
consolidated entrance-placement epic rather than five separate one-off fixes
if this is ever prioritized for a real fix.)

### J. Reconstructed "area" figures across this batch are not apples-to-apples with each other

Some per-design `notes` sum every modeled `Room` (including open-air car
porch, courtyard, and balcony rooms, which still have to be `Room` objects
so `render_pdf()` can draw their walls) into `reconstructed_gf_area_sqft`;
others explicitly exclude open-air rooms to match the site's declared
"built-up area," which is carpet/enclosed area only. Modern-18 and
Modern-23's reconstructed GF totals read as +27% over declared purely from
this inclusion difference — net of the same open rooms, both land within
±5%, in line with every other design in the batch. This is a reporting
inconsistency between individual reconstruction scripts, not a rendering
defect or a fidelity problem; it means **`reconstructed_*_area_sqft` values
across `re_data_modern_*.json` files should not be compared to each other
directly without first checking each design's `notes` for which convention
it used.** A future harness pass should standardize `save_design_json()` to
always report both an "all rooms" and an "enclosed only" total.

---

## Resolution status (2026-08-11)

Fixed on branch `fix/solver-limitations-render-pipeline` (plan: `docs/plans/2026-08-10-solver-limitations-render-pipeline-fixes.md`).

| Item | Status | Fix |
|---|---|---|
| #1, #5 | Fixed | orientation-aware stair treads (`_stair_tread_elements`) + floor-aware UP/DN labels in `pdf.py` |
| #2 | Fixed | `_NO_DOOR_TYPES` skip set in the `derive_openings` door loop |
| #3, H | Fixed | `section_cut_line()` mid-line fallback + `derive_section` Rule-7 stair guard |
| #6a | Fixed | `render_pdf()` iterates `ordered_floors()` (basement→SF); `arch_page_index()` keeps render-conditioning correct |
| #6c | Fixed | `derive_walls()` ring from room-union bbox (inner face flush; buildable fallback when no rooms) |
| #6, #6b, G, #6d | Surfaced | `FloorDrawing.diagnostics` carries per-room rejection reasons; placement redesign (#6d) deferred |
| F | Mitigated | `geometry:` out-of-bounds diagnostic in `build_floor_drawing` + corrected axis comments; field rename deferred |
| C | Fixed | `foyer` / `courtyard` / `wardrobe` RoomTypes (engine) + frontend labels/colors |
| J | Fixed | harness `save_design_json()` dual area totals (all-rooms + enclosed-only), local harness file |
| #4 | Out of scope | connectivity check deferred to `2026-08-09-layout-quality-critique-loop-design.md` |
| A, B, D, E | Out of scope | accepted schema limits / methodology notes — see plan |

Known follow-ups (not blockers): `foyer` ∈ `_WINDOW_TYPES` gap (openings-derived windows skip foyer; PDF symbol path covers it); interior-void orphan edges on partial footprints still draw as internal walls; openings surface model (`_exterior_edges`/`_place_main_entrance`) still keys off buildable plate, not the room-union ring.

