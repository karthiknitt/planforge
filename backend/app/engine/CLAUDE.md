# backend/app/engine — conventions

Geometry, layout generation, scoring, compliance, and drawing output. Prefer pure
functions over Shapely objects; keep I/O and persistence in `../services/`.

## Rules

- **Never do raw float math for polygon operations** — use Shapely. Floating-point edge
  cases in setback and inset logic have caused several solver bugs.
- **Compliance thresholds live in `backend/app/config/compliance_rules.json`**, never
  hardcoded (path confirmed by `compliance.py:8`; it is *not* `backend/config/`).
  That includes the Vastu rules — both `vastu_zones` (zone-keyed, three tiers:
  `preferred`/`avoid`/`prohibit`, though `check_vastu` reads only the latter two) and
  `vastu_room_rules` (room-type-keyed, three tiers: `preferred`/`acceptable`/`avoid`,
  read by `vastu_room_score`) — and opening standards. `vastu_room_rules` is a
  **derived transpose** of `vastu_zones`, pinned in both directions by the round-trip
  tests in `tests/test_vastu_score.py`: edit `vastu_zones` and re-derive, never author
  a `vastu_room_rules` cell by hand.
- **Never run `ruff format` on `*.json`** — it corrupts the rules file.
- **PDF generation is ReportLab only** — not matplotlib, not cairosvg.
- **DXF is ezdxf, and `doc.write()` needs `StringIO`** (text mode), not `BytesIO`.

## Layout paths

`solver.py` (OR-Tools CP-SAT) is the primary generator; `archetypes.py` is the fallback
when the solver cannot converge. **Changes to room-adjacency or door logic usually need
touching both** — a fix applied to only one path silently regresses the other.

`generator.py` orchestrates; `scorer.py` computes the 5-component layout score (natural
light, adjacency, aspect ratio, circulation, Vastu at 10% weight).

## Drawing pipeline

`plan_geometry.py` → walls, doors, windows, main-entrance pass (GF only).
`section_geometry.py` → SECTION A-A + FRONT ELEVATION, consumed by `section_render.py`
(IS 962 hatching) and both PDF generators.
`structural_grid.py` / `footing_placement.py` / `structural_drawing_set.py` feed the
structural sheets; member design itself happens in structapi, not here.

## Gotcha

OR-Tools 9.x: `new_interval_var(x, w, x + w, name)` fails because `x + w` is a two-IntVar
sum, not affine. Introduce an explicit end var: `model.add(ex == x + w)`.

`IntVar.proto.domain` does **not** honour negative indexing. It is a protobuf
repeated-scalar container, so `v.proto.domain[-1]` silently returns `0` instead
of the upper bound — no exception, just a wrong number. `tuple(v.proto.domain)`
is `(lo, hi)` and `v.proto.domain[0]` is correct. This has already cost one
mutation-testing round on the Vastu solver terms: a mutation written against
`domain[-1]` was a no-op and was scored as evidence of coverage it never
provided. Read bounds via `domain[0]` / `tuple(...)`, never a negative index.
