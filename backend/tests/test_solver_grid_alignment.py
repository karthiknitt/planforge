"""Solver column-grid alignment invariants (Phase 1A).

Pro-tester regression: rooms solved at slightly different widths put their
partition walls on near-miss coordinates; derive_columns then kept mid-span
T columns wherever dropping one left a beam run over max_beam_span_m. With
the wall-coalignment objective + post-solve snap pass, internal wall
centrelines must land on shared grid lines, interior columns must sit only
at true crossings or on the exterior ring, and GF/FF columns must stack.
"""

import math

import pytest

from app.engine.geometry import buildable_polygon
from app.engine.models import PlotConfig, Room
from app.engine.plan_geometry import derive_walls
from app.engine.solver import snap_rooms_to_shared_grid

EWT = 0.23

# Two internal wall lines on the same axis are either the SAME grid line
# (< NEAR_MISS_LO apart — float noise / orphan-vs-pair offsets) or a real
# structural bay (> NEAR_MISS_HI). Anything in between is a misalignment
# that splits the column grid.
NEAR_MISS_LO = 0.15
NEAR_MISS_HI = 0.50


def _cfg(**kwargs) -> PlotConfig:
    defaults = dict(
        plot_length=15.0,
        plot_width=12.0,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=0.9,
        setback_right=0.9,
        num_bedrooms=3,
        toilets=2,
        parking=True,
        city="other",
        road_side="S",
        vastu_enabled=False,
    )
    defaults.update(kwargs)
    return PlotConfig(**defaults)


def _room(rid: str, x: float, y: float, w: float, d: float, rtype="bedroom") -> Room:
    return Room(id=rid, name=rid, type=rtype, x=x, y=y, width=w, depth=d)


def _is_vertical(w) -> bool:
    return abs(w.x1 - w.x2) < 1e-9


def _internal_line_coords(rooms, buildable, vertical: bool) -> list[float]:
    walls = derive_walls(rooms, buildable, ewt=EWT)
    coords = {
        round(w.x1 if vertical else w.y1, 4)
        for w in walls
        if w.kind == "internal" and _is_vertical(w) == vertical
    }
    return sorted(coords)


@pytest.fixture(scope="module")
def solved_layouts():
    # Assert on the FULL pipeline output, not raw solve_layouts(): the
    # alignment guarantee lives at the generate() boundary since Phase 3 —
    # the solver is best-effort under a work budget (its incumbent may keep
    # a near-miss when a room at its spec minimum vetoes the snap merge),
    # and generate() re-snaps + merges junction columns AFTER the fill
    # passes, which is the geometry users, PDFs, and structapi consume.
    from app.engine.generator import generate

    layouts = generate(_cfg())
    assert layouts, "expected at least one generated layout for this fixture"
    return layouts


def test_internal_wall_lines_have_no_near_miss_offsets(solved_layouts):
    cfg = _cfg()
    buildable = buildable_polygon(cfg)
    for layout in solved_layouts:
        for fp in (layout.ground_floor, layout.first_floor):
            if not fp.rooms:
                continue
            near_misses = []
            for vertical in (True, False):
                coords = _internal_line_coords(fp.rooms, buildable, vertical)
                for a, b in zip(coords, coords[1:]):
                    gap = b - a
                    if NEAR_MISS_LO < gap < NEAR_MISS_HI:
                        near_misses.append(
                            ("v" if vertical else "h", a, b, round(gap, 3))
                        )
            # One residual pair per floor is legal: a room at its spec
            # minimum vetoes the snap merge (aligning would need a full
            # re-solve), and the column tests below keep the grid itself
            # clean. The pro-tester regression produced 3+ per floor.
            assert len(near_misses) <= 1, (
                f"layout {layout.id} floor {fp.floor}: misaligned partition "
                f"pairs splitting the column grid: {near_misses}"
            )


def test_all_columns_lie_on_shared_grid_lines(solved_layouts):
    # The pro-tester bug: columns on x/y lines no other column shares —
    # a private grid for one room. Every column must sit on a column line
    # (>= 2 columns within cluster tolerance) in BOTH axes, i.e. the
    # columns form one shared grid.
    grid_tol = 0.15
    cfg = _cfg()
    bx1, by1, bx2, by2 = buildable_polygon(cfg).bounds
    ring_x = (bx1 + EWT / 2, bx2 - EWT / 2)
    ring_y = (by1 + EWT / 2, by2 - EWT / 2)
    for layout in solved_layouts:
        for fp in (layout.ground_floor, layout.first_floor):
            if len(fp.columns) < 4:
                continue
            offgrid = []
            for c in fp.columns:
                # Exterior-ring columns live inside the perimeter wall —
                # always structurally justified, exempt from grid sharing.
                if any(abs(c.x - rx) <= 0.02 for rx in ring_x) or any(
                    abs(c.y - ry) <= 0.02 for ry in ring_y
                ):
                    continue
                x_shared = sum(1 for o in fp.columns if abs(o.x - c.x) <= grid_tol) >= 2
                y_shared = sum(1 for o in fp.columns if abs(o.y - c.y) <= grid_tol) >= 2
                if not (x_shared and y_shared):
                    offgrid.append((c.x, c.y))
            # At most ONE column per floor may sit off the shared grid: a
            # room pinched between its min/max width bounds can leave a
            # leftover strip whose orphan wall legitimately needs one
            # mid-beam support. The regression produced 3+ per floor.
            assert len(offgrid) <= 1, (
                f"layout {layout.id} floor {fp.floor}: columns on private "
                f"grid lines at {offgrid} — room widths should equalise so "
                "columns share one grid"
            )


def _is_archetype_layout(layout) -> bool:
    """Distinguish archetype-origin layouts from solver-origin ones.

    `generate()` reassigns layout ids to A/B/C by rank, so the id itself
    says nothing about origin (see the gotcha in test_stair_wet_separation.py)
    — but the two paths use disjoint room-id conventions:
    solver.py's `_build_room_list` emits bare ids (``living_0``, ``bedroom_0``,
    ``stair_0``), while archetypes.py prefixes every id with its floor
    (``gf_living``, ``ff_lounge``, ``gf_stair``). A ``gf_``/``ff_`` prefix
    anywhere in the layout is archetype-only.
    """
    return any(
        r.id.startswith(("gf_", "ff_"))
        for r in layout.ground_floor.rooms + layout.first_floor.rooms
    )


def _stacked_ratio(layout) -> float | None:
    gf = [(c.x, c.y) for c in layout.ground_floor.columns]
    ff = [(c.x, c.y) for c in layout.first_floor.columns]
    if not ff:
        return None
    stacked = sum(
        1 for fx, fy in ff if any(math.hypot(fx - gx, fy - gy) <= 0.15 for gx, gy in gf)
    )
    return stacked / len(ff)


def test_cross_floor_columns_stack(solved_layouts):
    for layout in solved_layouts:
        if _is_archetype_layout(layout):
            continue  # covered separately below, see _CROSS_FLOOR_ARCHETYPE_XFAIL
        ratio = _stacked_ratio(layout)
        if ratio is None:
            continue
        assert ratio >= 0.6, (
            f"layout {layout.id}: only {ratio:.2f} of first-floor columns "
            "land on ground-floor column positions"
        )


@pytest.mark.xfail(
    strict=True,
    reason="archetype layout_d's cross-floor stacking is improved (issue #51b "
    "aligned its living/parking <-> lounge/toilet joint) but still short of "
    "the 60% floor on its own — see issue #51 for the remaining gap "
    "(measured 6/13 ~= 0.46 after the joint-alignment fix). Remove this xfail "
    "once a further band-alignment fix closes it.",
)
def test_cross_floor_columns_stack_archetype(solved_layouts):
    for layout in solved_layouts:
        if not _is_archetype_layout(layout):
            continue
        ratio = _stacked_ratio(layout)
        if ratio is None:
            continue
        assert ratio >= 0.6, (
            f"layout {layout.id}: only {ratio:.2f} of first-floor columns "
            "land on ground-floor column positions"
        )


# ── snap_rooms_to_shared_grid unit tests ─────────────────────────────────────

_GENEROUS = {"min_width_m": 0.5, "min_depth_m": 0.5, "min_area_sqm": 0.25}


def test_snap_merges_near_aligned_edges():
    # Two stacked rooms whose right edges are 0.08 m apart -> one grid line.
    floors = [
        [
            _room("a", 1.0, 1.0, 3.00, 4.0),
            _room("b", 1.0, 5.115, 3.08, 4.0),
        ]
    ]
    snapped = snap_rooms_to_shared_grid(
        floors, {"a": _GENEROUS, "b": _GENEROUS}, tol=0.10
    )
    a, b = snapped[0]
    assert math.isclose(a.x + a.width, b.x + b.width, abs_tol=1e-6)


def test_snap_spans_floors():
    # GF and FF walls 0.09 m apart coalesce so columns stack vertically.
    floors = [
        [_room("g", 1.0, 1.0, 3.00, 4.0)],
        [_room("f", 1.0, 1.0, 3.09, 4.0)],
    ]
    snapped = snap_rooms_to_shared_grid(
        floors, {"g": _GENEROUS, "f": _GENEROUS}, tol=0.10
    )
    (g,), (f,) = snapped
    assert math.isclose(g.x + g.width, f.x + f.width, abs_tol=1e-6)


def test_snap_leaves_distinct_wall_faces_alone():
    # Facing edges across one internal wall differ by iwt (0.115) — they are
    # two faces of the SAME wall and must never merge into one coordinate.
    floors = [
        [
            _room("a", 1.0, 1.0, 3.0, 4.0),  # right edge 4.0
            _room("b", 4.115, 1.0, 3.0, 4.0),  # left edge 4.115
        ]
    ]
    snapped = snap_rooms_to_shared_grid(
        floors, {"a": _GENEROUS, "b": _GENEROUS}, tol=0.10
    )
    a, b = snapped[0]
    assert b.x - (a.x + a.width) > 0.10


def test_snap_respects_min_dims():
    # Room "small" sits at its exact minimum width; a snap that would shrink
    # it below spec must be reverted for that room.
    mins = {
        "small": {"min_width_m": 3.0, "min_depth_m": 0.5, "min_area_sqm": 0.25},
        "other": _GENEROUS,
    }
    floors = [
        [
            _room("small", 1.0, 1.0, 3.00, 4.0),
            _room("other", 1.0, 5.115, 2.91, 4.0),  # right edge 0.09 lower
        ]
    ]
    snapped = snap_rooms_to_shared_grid(floors, mins, tol=0.10)
    small = next(r for r in snapped[0] if r.id == "small")
    assert small.width >= 3.0 - 1e-9


def test_snap_never_creates_overlap():
    # Adversarial: clusters pull two facing edges toward each other by more
    # than their 0.115 gap; the snap must detect and revert the overlap.
    floors = [
        [
            _room("a", 1.0, 1.0, 3.00, 8.0),  # right edge 4.00
            _room("b", 4.115, 1.0, 3.0, 8.0),  # left edge 4.115
            # magnets: pull a's right edge up and b's left edge down
            _room("m1", 1.0, 9.115, 3.09, 2.0),  # right edge 4.09
            _room("m2", 4.03, 11.23, 3.0, 2.0),  # left edge 4.03
        ]
    ]
    mins = {r.id: _GENEROUS for r in floors[0]}
    snapped = snap_rooms_to_shared_grid(floors, mins, tol=0.10)
    rooms = snapped[0]
    for i, ra in enumerate(rooms):
        for rb in rooms[i + 1 :]:
            x_ov = min(ra.x + ra.width, rb.x + rb.width) - max(ra.x, rb.x)
            y_ov = min(ra.y + ra.depth, rb.y + rb.depth) - max(ra.y, rb.y)
            assert not (x_ov > 1e-6 and y_ov > 1e-6), (
                f"snap created overlap between {ra.id} and {rb.id}"
            )


def test_scorer_has_grid_regularity_component():
    from app.engine.models import ComplianceResult, FloorPlan, Layout
    from app.engine.scorer import score_layout

    cfg = _cfg(
        num_bedrooms=2, toilets=2, parking=False, plot_length=12.0, plot_width=9.0
    )
    rooms = [
        _room("l", 1.13, 1.73, 3.5, 4.0, "living"),
        _room("k", 4.745, 1.73, 2.0, 2.5, "kitchen"),
    ]
    layout = Layout(
        id="A",
        name="Layout A",
        ground_floor=FloorPlan(floor=0, floor_type="ground", rooms=rooms),
        first_floor=FloorPlan(floor=1, floor_type="first", rooms=[]),
        compliance=ComplianceResult(passed=True),
    )
    s = score_layout(layout, cfg)
    assert hasattr(s, "grid_regularity")
    assert 0 <= s.grid_regularity <= 100
    assert 0 <= s.total <= 100
