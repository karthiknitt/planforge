# PlanForge — Current State (as-built)

Written 2026-08-16, verified against `feat/solver-capability-uplift`. This document exists
because an external architecture review (August 2026) proposed 22 milestones from the README
and GitHub file listing rather than the source; roughly 40% were already built. Separately, a
reconnaissance pass over this repo's own implementation plan produced task briefs pointing at
`backend/app/render/`, a directory that does not exist. Both came from the same failure: no
accurate, current description of what PlanForge actually is. This is that description.

**On the line numbers below:** every one was checked against this exact commit before this
document was written (see the verification note at the end of each section, or the report
this task produced). Line numbers drift as the branch evolves — several in the source task
brief for this document were already stale, some by 300+ lines, because `plan_geometry.py` has
been rewritten twice on this branch. Where a reference is likely to move again, this document
names the **symbol** first and gives the line as a convenience, not an identifier. Treat any
number here that looks wrong as a signal the code moved, not that the claim is false — check
the symbol.

## The canonical drawing model: `FloorDrawing`

`FloorDrawing` (`backend/app/engine/cad_elements.py:117`) is the single geometric model that
every architectural drawing renderer consumes. It is built by
`build_floor_drawing()` (`backend/app/engine/plan_geometry.py`) from a floor's `rooms`, and
holds walls, openings, columns, junctions, dimension chains, labels, and the stair — nothing
else. Verified consumers, all going through `build_floor_drawing`:

- `backend/app/engine/pdf.py` — `_draw_floor_projected()` (line 1584, docstring at 1595):
  "Architectural floor page rendered purely from the canonical FloorDrawing."
- `backend/app/engine/cad_primitives.py` (line 11) — beam/column layout projected from it
- `backend/app/engine/section_geometry.py:204` and `:307` — both section-cut entry points call
  `build_floor_drawing(fp, cfg)` per floor
- `backend/app/quality/ccqs.py:316`, inside `compute_gcs()` (defined line 309)
- `backend/app/api/routes/export.py` — three call sites (lines 217, 516, 646)
- `frontend/src/components/floor-plan-svg.tsx:754` — the frontend's SVG renderer draws from
  the *same* backend-computed geometry (fetched, not recomputed), per its own comment at
  line 752: "Canonical drawing renderers ... FloorDrawing (app.engine.plan_geometry.
  build_floor_drawing) — the same geometry the PDF/DXF exports draw."

This is the load-bearing architectural fact of the drawing pipeline: PDF, DXF, section, GCS
scoring, and the frontend SVG preview all render the *same* wall/opening/column geometry
computed once on the backend. There is no separate frontend geometry engine for these
elements. (Room fills, labels, furniture and edit-mode interaction are the exception — see
"Site context and furniture" below.)

## Walls and openings are derived, never persisted

`derive_walls()` (`backend/app/engine/plan_geometry.py:619`) and `derive_openings()`
(`backend/app/engine/plan_geometry.py:1553`) compute wall centrelines and door/window/vent
placements from `rooms` on every read. Neither is stored in the database or on the `Layout`
model — only room rectangles are persisted.

Why: PlanForge's reproducibility guarantee — same input, same output, required for revisions,
approvals and BOQ — rests on walls being a pure function of rooms. Persisting wall geometry
alongside rooms would let the two drift out of agreement (a room edited without its walls
being regenerated), which is exactly the class of bug a derived-geometry model prevents by
construction. This rationale is recorded in the branch's own implementation plan
(`docs/superpowers/plans/2026-08-15-solver-capability-uplift.md`, Task 26 preamble).

## No entity identity on walls or openings

`WallSegment` (`cad_elements.py:17`) and `Opening` (`cad_elements.py:47`) are geometry-only
dataclasses — endpoints, thickness, kind, swing data. Neither carries an `id` field; verified
by reading both class bodies in full. `WallJunction` and `LabelBox` similarly carry no
identity beyond `room_id` where relevant.

Consequence: any AI tool or UI feature that needs to reference "this specific wall" or "this
specific opening" across edits (e.g. "widen the window nearest the kitchen sink") has no
stable handle to do so — walls and openings are recomputed from scratch on every
`derive_walls`/`derive_openings` call, so even a topologically-identical wall gets a fresh,
unaddressable object each time. This is unimplementable today; the branch's own plan assigns
it to two not-yet-run tasks: Task 26 (deterministic wall IDs, derived from topology — the
separated room-id pair for internal walls) and Task 27 (deterministic opening IDs derived from
host wall ID + position, plus promoting the opening schedule marks that currently live inline
in `pdf.py` out to a shared location). Neither has executed as of this document.

## Units: metres as `float`

The engine represents all geometry in metres as Python `float` throughout — rooms, walls,
openings, the plot polygon. An integer-millimetre migration was considered and **rejected**:
per the plan's own accounting, it would touch ~17,000 engine lines and 100 test files for no
user-visible benefit, and it would reintroduce the double-rounding defect class that a
previous fix (Task 6, this branch) closed. This is a deliberate, standing decision, not an
oversight — see `docs/superpowers/plans/2026-08-15-solver-capability-uplift.md` (search
"integer millimetres").

## Coordinate convention

Lifted verbatim from the `backend/app/engine/geometry.py` module docstring — this is the
single normative statement of the convention; do not restate it independently elsewhere:

> Coordinate system: x grows left->right (0..plot_width), y grows front/road -> rear
> (0..plot_length). Edge setbacks are classified by the edge's outward normal: -y => front,
> +y => rear, -x => left, +x => right (dominant axis for slanted edges).

`plot_polygon()` and `buildable_polygon()` (same module) are the single source of truth for
per-edge setbacks. Per that module's own docstring, this replaced four call sites that
previously computed the buildable boundary independently with different approximations
(solver/compliance/archetypes applying one averaged setback as a uniform buffer, `rooms.py`
using a plain rectangle, trapezoid plots falling through to full rectangles) — everything now
derives from these two functions.

## The 12 AI agent tools and the stream-error-chunk gotcha

`frontend/src/app/api/agent/[projectId]/route.ts` defines 12 semantic tools for the agent
chat, all AI SDK v6 `tool()` calls: `get_room_list` (77), `get_room_details` (85),
`get_compliance_status` (92), `run_structural_design` (98), `get_available_space` (126),
`move_room` (135), `resize_room` (149), `swap_rooms` (167), `add_room` (180),
`remove_room` (198), `undo_last_change` (207), `refresh_layout` (216).

None of these operate on individual walls or openings — consistent with "no entity identity"
above; the tool surface is room-level.

The stream-error-chunk gotcha is stated directly at its true origin, `route.ts:343-345`: "In
ai@6 a provider failure surfaces as an `error` CHUNK (never a thrown rejection), so the raw
error is captured via toUIMessageStream's onError — runModelChain reads it to decide whether
to fall back to the next provider." `agent-model-chain.ts`'s `StreamAttempt.getRawError` JSDoc
(lines 17-22) restates the same mechanism from the consumer side: "The raw provider error
captured while streaming (via toUIMessageStream's onError) ... Populated by the time an
`error` chunk is yielded, since onError runs to build that chunk." The consequence, per
`consumeAttempt`'s own comment (lines 62–66):
"In ai@6 provider failures arrive as `error` CHUNKS (never thrown), but the try/catch is kept
as a belt-and-braces guard for a genuinely rejecting iterable." In other words, catch-based
fallback logic is dead code *for the failure mode that actually occurs in production*
(provider errors) — the try/catch itself is kept only as a defensive guard against a
different, rarer failure mode (an iterable that genuinely throws). The real fallback path
works by inspecting chunk types as they stream: "Non-error chunks are forwarded immediately;
the first error chunk stops consumption and surfaces the raw error" (`consumeAttempt`,
line 67).

## Structural model

`StructuralModel` (`backend/app/engine/structural_data.py:151` — not line 50; that line
number in earlier drafts of this document was wrong) is the typed model backing the
structural drawing set. `structural_drawing_set.py`'s own module docstring (line 1) describes
the output as "the 12-sheet construction-grade PDF," but the actual sheet count is not fixed
at 12: `_sheet_sequence()` (`structural_drawing_set.py:58`) builds 6 fixed sheets (general
notes, column/footing plan, footing details, column details, plinth beam plan, plinth beam
details), then appends 2 sheets per floor from `model.floors` (framing plan + framing
details), then 2 more fixed sheets (slab reinforcement, staircase details) — 8 fixed + 2×floor
count. "12 sheets" is the number for the common two-floor case, not a hard constant.

`ColumnItem.bars` is a plain `str` (e.g. `"3T20"`) and `design` is an opaque `dict` on
`ColumnItem`, `FootingItem`, `BeamRun` and `SlabPanel` (`structural_data.py:80-81` and
surrounding fields) — verified by reading the dataclass fields directly. Task 31 (typed
structural detailing model, not yet run) replaces these with typed `BarGroup`, `Stirrup`,
`Lap`, `Cover` entities, keeping `design: dict` alongside during migration as the raw payload.

## GCS supersedes CCQS as the export gate

`compute_gcs()` (`backend/app/quality/ccqs.py:309`, `GCS_MAX = 100` at line 145) is the live
export quality gate, computed directly from the canonical `FloorDrawing` rather than from
rendered pixels or text. The module's own comment block immediately above `GCS_MAX` (lines
135–142) states the reason plainly: `compute_ccqs_deterministic()` (line 121)'s 80
deterministic points are "gameable regex/pixel checkboxes maxed out early," and its remaining
20 points (a stochastic vision-judge call) "plateaued near 16/20 regardless of real
drawing-quality changes."

**Correction to a common assumption:** CCQS is not dead code. The same comment block says it
is "kept as-is (still used by GET /layouts/{id}/quality) pending a separate decision on full
deprecation." Anything measuring drawing quality for gating purposes should use GCS; CCQS
remains live for that one read endpoint.

## Site context and furniture bypass the canonical model

`FloorDrawing` covers walls, openings, columns, junctions, dimension chains, labels and the
stair — the elements listed above. The compound wall, the landscaped setback fill, and
furniture are **not** part of it; they are drawn per-renderer, straight from `rooms`, in each
export format independently. This asymmetry is why the compound wall and setback fill appear
in the DXF output but not the PDF, and why furniture is implemented twice: 12 `_furniture_*`
renderer functions in `backend/app/engine/cad_advanced.py` for DXF, and an independent
implementation in `frontend/src/components/floor-plan-svg.tsx` plus `furniture-overlay.tsx`
for the frontend SVG. A later phase of the current plan is scoped to close this gap; it has
not run as of this document.

## Verified dead code in `cad_elements.py` (Task 9C target — not yet removed)

Eight symbols in `backend/app/engine/cad_elements.py` have zero references anywhere in
`backend/` or `frontend/` outside their own declarations in that file — confirmed by grepping
the whole backend tree (including tests) and the whole frontend tree for each name
individually:

- `DoorSymbol` (line 142), `WindowSymbol` (153), `GridLine` (174), `DimensionLine` (185),
  `CADDrawing` (198) — dataclasses
- `build_dimensions()` (214), `build_columns()` (266), `build_windows()` (273) — functions

These are used only by each other inside the same file (e.g. `CADDrawing` fields typed as
`list[DimensionLine]`) and by nothing else in the codebase. One near-miss worth recording:
`frontend/src/components/floor-plan-svg.tsx` independently defines its own `WindowSymbol`
(a React component, line 232) and a `DrawingDoorSymbol` whose own comment calls out "unlike
the legacy DoorSymbol" (line 826) — these are unrelated, differently-implemented frontend
symbols that happen to share a name, not consumers of the backend dead code. None of the eight
backend symbols is actually live. Task 9C, which has not yet run as of this document, is
scoped to remove them.

`LabelBox` (`cad_elements.py:68`) is explicitly **not** part of this list — it is live,
consumed by `plan_geometry.py`, `quality/ccqs.py`, and `api/routes/export.py`, and stays.

## Test suite runtime and Task 9A

The full backend test suite takes **~68 minutes** to run end to end — the measured status quo
on this branch as of the plan's mid-execution checkpoint (`.superpowers/sdd/
2026-08-15-solver-capability-uplift/progress.md`), which already invalidated running the full
suite per task. Task 9A ("cut the test-suite runtime") is running concurrently with this
document's own writing, dispatched to establish that measurement and a fast-path
classification for future tasks. Its outcome is not yet known and is not asserted here.

## Accepted limitations

A few gaps are deliberate, not oversights:

- **No FreeCAD backend.** A B-rep CAD kernel was evaluated and rejected for the MVP — 5–15s
  cold start, 300–500MB per process, not thread-safe; deferred to post-MVP as an optional
  export-only step. (Recorded in `docs/freecad-backend-tradeoffs.md` on the primary checkout —
  note this file is `git`-untracked by design, kept on disk locally rather than committed, so
  it will not appear in a fresh clone or a separate worktree such as this one.)
- **IFC round-trip: null result.** An IfcOpenShell-based round-trip experiment did not clear
  the CCQS bar the existing Shapely+ezdxf pipeline already met (96/96), and was not pursued
  further. No file in this worktree documents it; the finding lives in session history rather
  than the repo.
- **Arcs are render-only.** DXF furniture symbols use real arc primitives (e.g. `msp.add_arc`
  in `backend/app/engine/cad_advanced.py`, sink/bowl details around lines 578 and 762) — but
  arcs exist only in the rendered output, not in the solver's or `FloorDrawing`'s geometric
  model, which is axis-aligned segments.
- **Style presets are soft defaults, not enforced constraints.** `DEFAULT_STYLE` in
  `backend/app/engine/render_prompt.py` (line 10) is a text hint fed into the AI image-render
  prompt ("photorealistic top-down 3D architectural visualization..."); it shapes what the
  image model is asked for, not a constraint the renderer enforces.
- **Three known solver/render gaps**, tracked in
  `docs/superpowers/specs/solver_limitations.md` under "Hard schema limits" and
  "Bulk-reconstruction findings": (B) `PlotConfig` carries solver-input-shaped fields that
  aren't all render-consumed; (D) straightening jogged source layouts into rectilinear columns
  during reconstruction inflates measured area; (E) two-toilet-on-ground-floor plans are
  common in the training corpus but easy to mis-scope during reconstruction.
