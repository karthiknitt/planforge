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

from app.engine.models import PlotConfig
from app.engine.solver import _forbid_notch, _PartVars, solve_layout


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
        plot_length=15.0,
        plot_width=12.0,
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
    nx0 = cfg.plot_width - cfg.notch_width
    ny0 = cfg.plot_length - cfg.notch_depth
    for fp in (layout.ground_floor, layout.first_floor):
        for r in fp.rooms:
            for p in r.rects:
                ox = max(0.0, min(p.x + p.width, cfg.plot_width) - max(p.x, nx0))
                oy = max(0.0, min(p.y + p.depth, cfg.plot_length) - max(p.y, ny0))
                assert ox * oy < 1e-6, f"{r.id} part {p} intrudes into the notch"


def test_l_plot_still_houses_the_full_programme():
    """Regression on the old delete-after-the-fact behaviour: bedroom count
    must survive."""
    cfg = _l_cfg()
    layout = solve_layout(cfg)
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
