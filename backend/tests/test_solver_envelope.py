"""Rectilinear PLOT envelope: room parts may not enter the plot's notch.

An L/T plot is a rectangle with a corner cut out. That cutout is *off-plot
land*, so it must be forbidden to the solver as a hard constraint. Previously
`generator.py` placed rooms across the whole rectangle and then DELETED the
ones that landed in the cutout, silently losing programme — a 3-bedroom
request could come back with 2.

Plot shape is independent of ROOM shape: these tests never set
`allow_shape_templates`, so every room here is a plain RECT and the notch
constraint is exercised on ordinary rectangles.
"""

from __future__ import annotations

import pytest
from ortools.sat.python import cp_model
from shapely.geometry import box

from app.engine.geometry import buildable_polygon, notch_keepout, notch_rect
from app.engine.models import PlotConfig
from app.engine.solver import (
    _forbid_notch,
    _PartVars,
    _plate_geom_mm,
    notch_rect_m,
    solve_layout,
    validate_plot_envelope,
)

EWT = 0.23  # external wall thickness, metres (compliance_rules default)


def _a_part(model: cp_model.CpModel, room_type: str) -> _PartVars:
    """One free part of `room_type`, spanning a 12 x 15 m plate."""
    return _PartVars(
        model.new_int_var(0, 12_000, f"x_{room_type}"),
        model.new_int_var(0, 15_000, f"y_{room_type}"),
        model.new_int_var(1, 12_000, f"w_{room_type}"),
        model.new_int_var(1, 15_000, f"d_{room_type}"),
        f"{room_type}_0",
        room_type,
    )


def _l_cfg() -> PlotConfig:
    return PlotConfig(
        plot_y_extent=15.0,
        plot_x_extent=12.0,
        setback_front=3.0,
        setback_rear=1.5,
        setback_left=1.2,
        setback_right=1.2,
        num_bedrooms=3,
        toilets=2,
        parking=True,
        plot_template="L",
        notch_width=3.0,
        notch_depth=4.0,
    )


def test_no_room_part_enters_the_plot_notch():
    """The notch is the rear-right cutout of an L plot. Nothing may occupy it —
    previously rooms were placed there and deleted afterwards, silently losing
    programme."""
    cfg = _l_cfg()
    layout = solve_layout(cfg)
    assert layout is not None
    nx0 = cfg.plot_x_extent - cfg.notch_width
    ny0 = cfg.plot_y_extent - cfg.notch_depth
    for fp in (layout.ground_floor, layout.first_floor):
        for r in fp.rooms:
            for p in r.rects:
                ox = max(0.0, min(p.x + p.width, cfg.plot_x_extent) - max(p.x, nx0))
                oy = max(0.0, min(p.y + p.depth, cfg.plot_y_extent) - max(p.y, ny0))
                assert ox * oy < 1e-6, f"{r.id} part {p} intrudes into the notch"


def test_l_plot_still_houses_the_full_programme():
    """Regression on the old delete-after-the-fact behaviour: bedroom count
    must survive."""
    cfg = _l_cfg()
    layout = solve_layout(cfg)
    assert layout is not None, (
        "solve_layout returned None (infeasible or non-OPTIMAL/FEASIBLE)"
    )
    beds = [
        r
        for fp in (layout.ground_floor, layout.first_floor)
        for r in fp.rooms
        if r.type in ("bedroom", "master_bedroom")
    ]
    assert len(beds) == cfg.num_bedrooms


def test_rect_plot_unchanged():
    cfg = _l_cfg()
    cfg.plot_template = "RECT"
    assert solve_layout(cfg) is not None


def test_forbid_notch_is_a_no_op_on_a_rect_plot():
    """`plot_template="RECT"` (the default) must leave the CP-SAT model
    byte-identical: no extra BoolVars, no extra constraints, nothing.

    A behavioural `solve_layout(...) is not None` check cannot see a model that
    merely got *bigger*; comparing the serialised proto can.
    """
    cfg = _l_cfg()
    cfg.plot_template = "RECT"

    model = cp_model.CpModel()
    parts = [_a_part(model, "bedroom")]

    before = str(model.proto)
    _forbid_notch(model, cfg, parts, ox_mm=0, oy_mm=0, bw=10_000, bd=10_000)
    after = str(model.proto)

    assert after == before


@pytest.mark.parametrize(
    "room_type",
    ["bedroom", "parking", "balcony", "garden", "terrace", "courtyard"],
)
def test_no_room_type_is_exempt_from_the_notch(room_type: str):
    """The notch is off-plot land, so *every* type is constrained — open and
    outdoor types included. PR #81's parking exemption was about reachability
    from a driveway; a car porch still stands on land you own, the notch is
    land you do not.

    Asserted on the MODEL, not on a solve: whether a solved layout happens to
    place a balcony near the notch depends on the objective, so a solve-based
    check would pass vacuously for any type the solver kept far away.
    """
    cfg = _l_cfg()
    model = cp_model.CpModel()
    parts = [_a_part(model, room_type)]

    _forbid_notch(model, cfg, parts, ox_mm=0, oy_mm=0, bw=12_000, bd=15_000)

    # rear-right corner notch ⇒ exactly two escape directions, both emitted
    lits = [v.name for v in model.proto.variables if v.name.startswith("notch_")]
    assert sorted(lits) == [
        f"notch_front_{room_type}_{room_type}_0_0",
        f"notch_left_{room_type}_{room_type}_0_0",
    ]
    assert len(model.proto.constraints) == 3  # 2 reified bounds + 1 bool_or


def test_an_oversized_notch_raises_a_named_validation_error():
    """A notch that eats the buildable plate is a user-input problem: it must
    surface as a clear error naming the shortfall, not be silently relaxed and
    not be swallowed into a bare `None`."""
    cfg = _l_cfg()
    cfg.notch_width = 11.0
    cfg.notch_depth = 14.0
    with pytest.raises(ValueError) as exc:
        solve_layout(cfg)
    msg = str(exc.value)
    assert "notch" in msg.lower()
    assert "m²" in msg or "sqm" in msg


def test_a_degenerate_notch_is_rejected():
    """`plot_template != "RECT"` with a zero/negative notch is a malformed
    request, not a silent RECT."""
    cfg = _l_cfg()
    cfg.notch_depth = 0.0
    with pytest.raises(ValueError):
        solve_layout(cfg)


# ── Review fixes ──────────────────────────────────────────────────────────────


def _legacy_l_cfg() -> PlotConfig:
    """The reviewer's repro: a realistic, DB-persistable LEGACY l_shaped config.

    Same plot and programme as `_l_cfg`, expressed through the old
    `plot_shape`/`cutout_*` fields instead of `plot_template`/`notch_*`.
    """
    return PlotConfig(
        plot_y_extent=15.0,
        plot_x_extent=12.0,
        setback_front=3.0,
        setback_rear=1.5,
        setback_left=1.2,
        setback_right=1.2,
        num_bedrooms=3,
        toilets=2,
        parking=True,
        plot_shape="l_shaped",
        cutout_corner="NE",
        cutout_width=3.0,
        cutout_height=4.0,
    )


def test_legacy_l_shaped_config_is_not_gated_by_the_validator():
    """FINDING 1. The legacy surface is user-reachable and DB-persisted, and no
    route from `generate` down to generate/export/share/revisions/structural
    handles a ValueError. Gating it turned saved projects into an uncaught 500
    where they used to degrade to an empty layout list.
    """
    cfg = _legacy_l_cfg()
    validate_plot_envelope(cfg, EWT)  # must not raise


def test_legacy_l_shaped_config_solves_without_an_unhandled_raise():
    """FINDING 1, at the entry point that `generate` uses the same guard for."""
    cfg = _legacy_l_cfg()
    layout = solve_layout(cfg)  # None is fine; an escaping exception is not
    assert layout is None or layout.ground_floor is not None


def test_legacy_l_shaped_is_notch_safe_via_its_inset_not_via_the_constraint():
    """TRAP NOTICE for whoever fixes `geometry.buildable_polygon`.

    An earlier version of this test asserted only
    `notch_rect_m(cfg) == (9.0, 11.0, 12.0, 15.0)` and claimed the legacy
    surface "still gets the notch constraint". Both were wrong: that assertion
    stays green even if the `_forbid_notch` call is deleted from `_solve_one`
    outright, and on the real solve geometry the constraint emits NOTHING.

    What actually keeps legacy L plots out of their cutout is the *bug* in
    `buildable_polygon`: its half-plane inset over-clips the plate to
    6140x6040 mm at (1430, 3230), whose right edge is x=7.57 m — already short
    of the notch at x=9.0 m. So `_forbid_notch` takes its "the notch misses the
    buildable plate entirely" early return and adds zero literals.

    Task 9 deleted generator.py's post-hoc "delete rooms in the cutout" pass,
    so this inset is now the ONLY thing standing between a legacy config and a
    room in the cutout. Correcting the inset without re-checking this will
    silently re-open room-in-cutout placement. The third assertion below is the
    safety net: it shows the constraint is correctly wired and DOES engage once
    the plate is the honest one, so a fixed inset is caught by the machinery
    rather than by a user.
    """
    cfg = _legacy_l_cfg()

    def _emitted(bw: int, bd: int, ox: int, oy: int) -> tuple[int, int]:
        model = cp_model.CpModel()
        parts = [
            _PartVars(
                model.new_int_var(0, bw, "x"),
                model.new_int_var(0, bd, "y"),
                model.new_int_var(1, bw, "w"),
                model.new_int_var(1, bd, "d"),
                "bedroom_0",
                "bedroom",
            )
        ]
        _forbid_notch(model, cfg, parts, ox_mm=ox, oy_mm=oy, bw=bw, bd=bd, ewt=EWT)
        literals = [v for v in model.proto.variables if v.name.startswith("notch_")]
        return len(literals), len(model.proto.constraints)

    bw, bd, ox, oy = _plate_geom_mm(cfg, EWT)[:4]

    # 1. the over-clipped plate the legacy surface actually solves on...
    assert (bw, bd, ox, oy) == (6140, 6040, 1430, 3230)
    # 2. ...already stops short of the notch, so the constraint is a no-op
    assert ox + bw <= 9000, "plate reaches the notch; assertion 3 is now load-bearing"
    assert _emitted(bw, bd, ox, oy) == (0, 0)
    # 3. but the constraint IS wired: give it the honest full-rectangle plate
    #    (what a corrected `buildable_polygon` would return) and it engages
    assert _emitted(9140, 10040, 1430, 3230) == (2, 3)


@pytest.mark.parametrize("template", ["T", "U"])
def test_t_and_u_plot_templates_are_rejected_not_silently_wrong(template: str):
    """FINDING 4. A T plot has a notch in each rear corner and a U plot a
    central one; `notch_rect_m` only knows the single rear-right cutout, so
    accepting them would under-constrain the model and hand the user a plan
    built on land they do not own."""
    cfg = _l_cfg()
    cfg.plot_template = template

    with pytest.raises(ValueError) as exc:
        validate_plot_envelope(cfg, EWT)
    assert "not supported" in str(exc.value)
    assert 'plot_template="L"' in str(exc.value)

    with pytest.raises(ValueError):
        solve_layout(cfg)
    # defence in depth: even reached directly, the geometry helper refuses
    with pytest.raises(ValueError):
        notch_rect_m(cfg)


def test_the_validator_never_measures_less_than_the_archetype_plate():
    """FINDING 2. The guard runs at `generate()`, which also feeds the archetype
    fallback, so it must measure the LARGER of the two plates or it rejects
    plots the archetypes could have built on."""
    from app.engine.archetypes import _floor_plate

    cfg = _l_cfg()
    bw, bd, ox, oy, _ = _plate_geom_mm(cfg, EWT)
    keepout = notch_keepout(cfg, wall_clearance=EWT)
    kx0, ky0, kx1, ky1 = keepout.bounds
    lost = max(0.0, min(ox / 1000 + bw / 1000, kx1) - max(ox / 1000, kx0)) * max(
        0.0, min(oy / 1000 + bd / 1000, ky1) - max(oy / 1000, ky0)
    )
    measured = (bw / 1000) * (bd / 1000) - lost

    plate = _floor_plate(cfg, EWT)
    assert measured >= plate.width * plate.depth


def test_the_new_surface_yields_a_notched_buildable_polygon():
    """FINDING 3. `plot_template` leaves `plot_shape == "rectangular"`, so
    without an explicit branch every boundary consumer sees the full rectangle.
    """
    cfg = _l_cfg()
    plate = buildable_polygon(cfg, wall_clearance=EWT)
    keepout = notch_keepout(cfg, wall_clearance=EWT)
    assert plate.intersection(keepout).area < 1e-9
    # ... and it is the exact region, not the over-clipped convex core the
    # half-plane inset produces on a non-convex outline (37.1 m²).
    assert plate.area == pytest.approx(79.77, abs=0.05)


def test_a_fill_pass_cannot_put_a_room_in_the_notch():
    """FINDING 3. The post-solve blank-area fill/absorb passes re-create rooms
    from leftover plate space; before this fix they could put one straight back
    into the notch `_forbid_notch` had just kept clear, and `compliance.check`
    could not see it either."""
    from app.engine.generator import _fill_blank_areas
    from app.engine.models import FloorPlan, Room

    cfg = _l_cfg()
    # one small room at the front-left, leaving the whole rear of the plate
    # (notch included) as blank area for the fill passes to claim
    fp = FloorPlan(
        floor=0,
        floor_type="ground",
        rooms=[
            Room(
                id="living_0",
                name="Living Room",
                type="living",
                x=1.43,
                y=3.23,
                width=4.0,
                depth=3.5,
            )
        ],
    )
    _fill_blank_areas(fp, cfg, EWT, is_topmost=False)

    assert len(fp.rooms) > 1, "no fill happened — the assertion below is vacuous"
    keepout = notch_keepout(cfg, wall_clearance=EWT)
    for r in fp.rooms:
        for p in r.rects:
            overlap = keepout.intersection(
                box(p.x, p.y, p.x + p.width, p.y + p.depth)
            ).area
            assert overlap < 1e-6, f"fill pass put {r.id} in the notch keep-out"


def test_the_solver_respects_the_notch_setbacks_not_just_the_raw_notch():
    """The solver, compliance and the fill passes must share ONE definition of
    where the notch starts, or the solver parks a room flush against a plot
    boundary that compliance then fails it for."""
    cfg = _l_cfg()
    layout = solve_layout(cfg)
    assert layout is not None
    keepout = notch_keepout(cfg, wall_clearance=EWT)
    for floor_plan in (layout.ground_floor, layout.first_floor):
        for r in floor_plan.rooms:
            for p in r.rects:
                overlap = keepout.intersection(
                    box(p.x, p.y, p.x + p.width, p.y + p.depth)
                ).area
                assert overlap < 1e-6, f"{r.id} sits inside the notch setback"


@pytest.mark.parametrize("shape", ["trapezoid", "quadrilateral", "l_shaped"])
def test_a_notch_on_a_non_rectangular_plot_shape_raises(shape: str):
    """BREAKAGE 3. Every consumer models the notch as a corner cut out of a
    RECTANGLE — `plot_polygon` builds its hexagon from plot_width/plot_length
    and `buildable_polygon` insets a plain box — so combining the two surfaces
    would silently discard the trapezoid/quad/l_shaped outline and draw the
    plan on a plot the user does not have. Unreachable until Task 22 plumbs the
    fields through; a refusal beats a wrong answer."""
    cfg = _l_cfg()
    cfg.plot_shape = shape

    for call in (
        lambda: notch_rect(cfg),
        lambda: notch_keepout(cfg, wall_clearance=EWT),
        lambda: buildable_polygon(cfg, wall_clearance=EWT),
        lambda: validate_plot_envelope(cfg, EWT),
    ):
        with pytest.raises(ValueError, match="cannot be combined with"):
            call()
