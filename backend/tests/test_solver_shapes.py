"""CP-SAT no-overlap runs over room PARTS, not room bounding boxes.

Task 6 made a Room the union of 1-3 rectangles (`Room.rects`); until now the
solver still created exactly one x/y interval pair per room, so it could only
ever place rectangles. These tests pin the part-level model: templated rooms
may interlock (an L's notch filled by a neighbour), and the feature stays
strictly opt-in behind `PlotConfig.allow_shape_templates`.
"""

from __future__ import annotations

from ortools.sat.python import cp_model

from app.engine.models import Layout, PlotConfig, Room
from app.engine.shapes import Rect
from app.engine.solver import (
    _FRACTION_SCALE,
    _add_room_parts,
    _fit_template,
    _PartVars,
    _unit_parts_mm,
    solve_layout,
)


def _cfg(**kw) -> PlotConfig:
    base = dict(
        plot_length=15.0,
        plot_width=9.0,
        setback_front=3.0,
        setback_rear=1.5,
        setback_left=1.2,
        setback_right=1.2,
        num_bedrooms=3,
        toilets=2,
        parking=True,
    )
    base.update(kw)
    return PlotConfig(**base)


def _floors(layout: Layout) -> list[list[Room]]:
    return [layout.ground_floor.rooms, layout.first_floor.rooms]


def _parts_per_floor(layout: Layout) -> list[list[Rect]]:
    """Parts grouped BY FLOOR.

    Deliberately not one flat list across both floors: a ground-floor and a
    first-floor room occupying the same plan position is the normal case (they
    are stacked, not colliding), so a flat list would assert an invariant the
    solver neither has nor should have.
    """
    return [[p for r in rooms for p in r.rects] for rooms in _floors(layout)]


def _overlap(a: Rect, b: Rect) -> float:
    ox = max(0.0, min(a.x + a.width, b.x + b.width) - max(a.x, b.x))
    oy = max(0.0, min(a.y + a.depth, b.y + b.depth) - max(a.y, b.y))
    return ox * oy


def _geometry(layout: Layout) -> list[tuple]:
    return [
        (r.id, r.x, r.y, r.width, r.depth, r.template)
        for rooms in _floors(layout)
        for r in rooms
    ]


_ROOMY = dict(
    min_w=2_000,
    max_w=8_000,
    min_d=2_000,
    max_d=8_000,
    min_area=12_000_000,
    max_area=40_000_000,
)  # a living-room-sized spec in mm / mm², with plenty of headroom


def _area_fraction(template: str, ratio: float) -> float:
    unit = _unit_parts_mm(template, ratio)
    return sum(w * d for _, _, w, d in unit) / float(_FRACTION_SCALE**2)


def test_fit_template_inflates_the_bbox_minima_for_the_missing_notch():
    """The solver's area/width constraints are written on the BOUNDING BOX.

    A templated room only occupies a fraction of that box, and its narrow leg
    is only `ratio` of its width — so both minima must be inflated, or an
    L-shaped living room ships under its spec while the model believes it is
    compliant.
    """
    fit = _fit_template("L", 0.6, **_ROOMY)
    assert fit.template == "L"
    frac = _area_fraction("L", 0.6)
    assert frac < 1.0
    assert fit.min_area > _ROOMY["min_area"], "bbox area minimum was not inflated"
    assert fit.min_area * frac >= _ROOMY["min_area"] - 1
    assert fit.min_w > _ROOMY["min_w"], "bbox width minimum was not inflated"
    assert fit.min_w * 0.6 >= _ROOMY["min_w"] - 1, "the narrow leg is under spec"


def test_fit_template_degrades_to_rect_when_the_template_cannot_fit():
    """Templates must never be the reason a solve goes infeasible."""
    tight = dict(_ROOMY, max_w=2_100, max_d=2_100)
    fit = _fit_template("L", 0.6, **tight)
    assert fit.template == "RECT"
    assert (fit.min_w, fit.min_d) == (tight["min_w"], tight["min_d"])
    assert (fit.min_area, fit.max_area) == (tight["min_area"], tight["max_area"])
    assert (fit.grid_x, fit.grid_y) == (1, 1)


def test_fit_template_grid_step_makes_every_part_offset_a_whole_millimetre():
    """Part coords are `dim * u / 1000`; CP-SAT is integer-only.

    Without the grid step those equalities are only satisfiable for dimensions
    that happen to divide, silently amputating the domain (or going infeasible).
    """
    fit = _fit_template("L", 0.6, **_ROOMY)
    for ux, uy, uw, ud in _unit_parts_mm("L", 0.6):
        assert (fit.min_w * ux) % _FRACTION_SCALE == 0
        assert (fit.min_w * uw) % _FRACTION_SCALE == 0
        assert (fit.min_d * uy) % _FRACTION_SCALE == 0
        assert (fit.min_d * ud) % _FRACTION_SCALE == 0
    assert fit.min_w % fit.grid_x == 0
    assert fit.min_d % fit.grid_y == 0


def test_unit_parts_tile_the_bounding_box_without_overlapping():
    for template in ("RECT", "L", "T", "U"):
        parts = _unit_parts_mm(template, 0.6)
        for i, (ax, ay, aw, ad) in enumerate(parts):
            for bx, by, bw, bd in parts[i + 1 :]:
                assert not (
                    min(ax + aw, bx + bw) > max(ax, bx)
                    and min(ay + ad, by + bd) > max(ay, by)
                ), f"{template}: rounded parts overlap — the model would be infeasible"


def _fixed(model: cp_model.CpModel, value: int, name: str) -> cp_model.IntVar:
    return model.new_int_var(value, value, name)


def test_a_neighbour_can_occupy_an_l_rooms_notch():
    """The capability Task 8 exists for, isolated to the model.

    A plate exactly the size of one L-shaped room: the ONLY free space is that
    room's notch. With one interval pair per room (the pre-Task-8 model) the
    neighbour has nowhere to go and the model is infeasible; with one pair per
    PART it slots into the notch. `test_no_two_parts_overlap` cannot catch
    this — bbox-level no-overlap is strictly *stronger* than part-level, so
    reverting to it keeps every part disjoint and merely forbids interlocking.
    """
    model = cp_model.CpModel()
    x_ivs: list[cp_model.IntervalVar] = []
    y_ivs: list[cp_model.IntervalVar] = []
    part_vars: list[_PartVars] = []

    # L over a 1000x1000 bbox at ratio 0.6 -> base (0,0,1000,600) + leg
    # (0,600,600,400), leaving a 400x400 notch at (600,600).
    _add_room_parts(
        model,
        "l_room",
        _fixed(model, 0, "lx"),
        _fixed(model, 0, "ly"),
        _fixed(model, 1000, "lw"),
        _fixed(model, 1000, "ld"),
        _fixed(model, 1000, "lxe"),
        _fixed(model, 1000, "lye"),
        "L",
        0.6,
        1000,
        1000,
        x_ivs,
        y_ivs,
        part_vars,
    )
    nx = model.new_int_var(0, 600, "nx")
    ny = model.new_int_var(0, 600, "ny")
    nxe = model.new_int_var(0, 1000, "nxe")
    nye = model.new_int_var(0, 1000, "nye")
    model.add(nxe == nx + 400)
    model.add(nye == ny + 400)
    _add_room_parts(
        model,
        "neighbour",
        nx,
        ny,
        _fixed(model, 400, "nw"),
        _fixed(model, 400, "nd"),
        nxe,
        nye,
        "RECT",
        0.6,
        1000,
        1000,
        x_ivs,
        y_ivs,
        part_vars,
    )
    model.add_no_overlap_2d(x_ivs, y_ivs)

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    status = solver.solve(model)

    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE), (
        "the neighbour could not be placed: no-overlap is still running over "
        "room bounding boxes, so the L's notch is unreachable"
    )
    assert (solver.value(nx), solver.value(ny)) == (600, 600)
    # 3 parts: the L's two, plus the neighbour's single one.
    assert len(part_vars) == 3


def test_snap_overlap_guard_measures_footprints_not_bounding_boxes():
    """The post-solve snap pass reverts any pair it considers overlapping.

    Two interlocked rooms have overlapping BOUNDING BOXES by construction, so
    a bbox test there would revert every interlock the solver just found —
    silently undoing Task 8 downstream of the model.
    """
    from app.engine.solver import _rooms_overlap

    l_room = Room(
        id="l",
        name="L",
        type="living",
        x=0.0,
        y=0.0,
        width=4.0,
        depth=4.0,
        template="L",
        shape_ratio=0.6,
    )
    in_notch = Room(  # sits inside the L's notch: bboxes overlap, parts do not
        id="n",
        name="N",
        type="study",
        x=2.4,
        y=2.4,
        width=1.6,
        depth=1.6,
    )
    on_the_leg = Room(  # genuinely on top of the L's leg
        id="c",
        name="C",
        type="study",
        x=0.0,
        y=2.4,
        width=1.6,
        depth=1.6,
    )

    assert not _rooms_overlap(l_room, in_notch)
    assert _rooms_overlap(l_room, on_the_leg)
    assert _rooms_overlap(in_notch, in_notch)


def test_no_two_parts_overlap():
    """The invariant that add_no_overlap_2d must now enforce at part level."""
    layout = solve_layout(_cfg(allow_shape_templates=True))
    assert layout is not None
    for parts in _parts_per_floor(layout):
        for i, a in enumerate(parts):
            for b in parts[i + 1 :]:
                assert _overlap(a, b) < 1e-6, f"parts overlap: {a} vs {b}"


def test_solver_remains_feasible_with_templated_rooms():
    layout = solve_layout(_cfg(allow_shape_templates=True))
    assert layout is not None
    assert len(layout.ground_floor.rooms) > 0


def test_templates_on_produces_at_least_one_non_rect_room():
    """Without this the whole feature could ship as unreachable dead code."""
    layout = solve_layout(_cfg(allow_shape_templates=True))
    assert layout is not None
    templates = {r.template for rooms in _floors(layout) for r in rooms}
    assert templates - {"RECT"}, f"no templated room was placed: {templates}"


def test_templated_room_area_still_meets_its_spec_minimum():
    """A non-RECT room's AREA is its part union, not its bounding box.

    The solver's min-area constraint is written on w*d, so a templated room
    must have its bbox requirement inflated by the template's area fraction —
    otherwise an L-shaped living room silently ships ~16% under spec.
    """
    from app.engine.solver import _load_specs

    specs = _load_specs()
    layout = solve_layout(_cfg(allow_shape_templates=True))
    assert layout is not None
    for rooms in _floors(layout):
        for r in rooms:
            if r.template == "RECT":
                continue
            spec = specs.get(r.type, specs["utility"])
            assert r.area >= spec["min_area_sqm"] - 1e-6, (
                f"{r.id} ({r.template}) union area {r.area} < spec min "
                f"{spec['min_area_sqm']}"
            )


def test_solver_is_deterministic_with_templates():
    """CP-SAT determinism: same config, same seed, same geometry."""
    a = solve_layout(_cfg(allow_shape_templates=True))
    b = solve_layout(_cfg(allow_shape_templates=True))
    assert a is not None and b is not None
    assert _geometry(a) == _geometry(b)


def test_templates_off_by_default_produces_only_rect_rooms():
    """Regression gate: the feature is opt-in, so existing behaviour is intact."""
    layout = solve_layout(_cfg())
    assert layout is not None
    for rooms in _floors(layout):
        for r in rooms:
            assert r.template == "RECT"


def test_vastu_disabled_leaves_the_model_unchanged():
    """Opt-in means opt-in: with the flag off the model is the pre-Task-8 one.

    One interval pair per ROOM (equivalently: exactly one part per room), and
    the same geometry as any other templates-off solve of the same config.
    """
    baseline = solve_layout(_cfg(vastu_enabled=False))
    again = solve_layout(_cfg())
    assert baseline is not None and again is not None
    for rooms in _floors(baseline):
        for r in rooms:
            assert len(r.rects) == 1, f"{r.id} contributed {len(r.rects)} intervals"
    assert _geometry(baseline) == _geometry(again)
