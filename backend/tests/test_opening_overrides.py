"""Opening override deltas (Phase 7 / Task 29).

An override lets a user or the AI move/resize/suppress ONE derived opening
without abandoning derivation: deltas ride on FloorPlan and are applied as
a post-pass inside build_floor_drawing(), so derive_openings() stays pure
and an unchanged layout re-derives byte-identically.

The GCS baseline cannot verify this feature — it has no positional-accuracy
metric, so an override that moves an opening to the WRONG place scores
identically to one that moves it correctly. Every assertion here pins
coordinates directly against frozen geometry.
"""

from app.engine.models import FloorPlan, OpeningOverride, PlotConfig
from app.engine.plan_geometry import build_floor_drawing
from app.services.layout_store import (
    engine_layout_from_geometry,
    layout_out_from_engine,
)

from tests.test_plan_geometry import _room


def _cfg() -> PlotConfig:
    return PlotConfig(
        plot_y_extent=15.0,
        plot_x_extent=9.0,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=1.0,
        setback_right=1.0,
        num_bedrooms=2,
        toilets=1,
        parking=False,
        num_floors=1,
    )


def _rooms():
    return [
        _room("a", 1.23, 7.73, 3.155, 6.04),
        _room("b", 4.5, 7.73, 3.27, 6.04),
        _room("c", 1.23, 1.73, 3.155, 5.885),
        _room("d", 4.5, 1.73, 3.27, 5.885),
    ]


def _fp(overrides: list[OpeningOverride] | None = None) -> FloorPlan:
    return FloorPlan(
        floor=0,
        floor_type="ground",
        rooms=_rooms(),
        opening_overrides=overrides or [],
    )


def _window(drawing):
    return next(o for o in drawing.openings if o.kind == "window")


def _wall_span(drawing, opening):
    vertical = not opening.is_horizontal
    coord = opening.cx if vertical else opening.cy
    ws = [
        w
        for w in drawing.walls
        if abs((w.x1 if vertical else w.y1) - coord) <= w.thickness / 2 + 0.01
        and (min(w.y1, w.y2) if vertical else min(w.x1, w.x2))
        <= (opening.cy if vertical else opening.cx)
        <= (max(w.y1, w.y2) if vertical else max(w.x1, w.x2))
    ]
    assert len(ws) == 1
    w = ws[0]
    lo_hi = tuple(sorted((w.y1, w.y2))) if vertical else tuple(sorted((w.x1, w.x2)))
    return w, lo_hi


def test_override_moves_exactly_one_window_to_asserted_coordinate():
    base = build_floor_drawing(_fp(), _cfg())
    win = _window(base)
    wall, (lo, hi) = _wall_span(base, win)
    target_along = (hi - lo) * 0.25
    moved = build_floor_drawing(
        _fp([OpeningOverride(opening_id=win.id, along=target_along)]), _cfg()
    )
    win2 = next(o for o in moved.openings if o.id == win.id)
    others_before = {
        o.id: (round(o.cx, 4), round(o.cy, 4), round(o.width, 4))
        for o in base.openings
        if o.id != win.id
    }
    others_after = {
        o.id: (round(o.cx, 4), round(o.cy, 4), round(o.width, 4))
        for o in moved.openings
        if o.id != win.id
    }
    assert others_before == others_after, "the override moved a second opening"
    if win.is_horizontal:
        assert win2.cx == (lo + target_along).__round__(6)
        assert win2.cy == win.cy
    else:
        assert win2.cy == (lo + target_along).__round__(6)
        assert win2.cx == win.cx


def test_override_resizes_width_and_keeps_wall_fit():
    base = build_floor_drawing(_fp(), _cfg())
    win = _window(base)
    wall, (lo, hi) = _wall_span(base, win)
    new_width = 0.8
    centre = (lo + hi) / 2
    moved = build_floor_drawing(
        _fp([OpeningOverride(opening_id=win.id, along=centre - lo, width=new_width)]),
        _cfg(),
    )
    win2 = next(o for o in moved.openings if o.id == win.id)
    assert win2.width == new_width
    # still fully inside the host wall
    span_lo, span_hi = lo, hi
    pos = win2.cx if win2.is_horizontal else win2.cy
    assert span_lo + new_width / 2 - 1e-6 <= pos <= span_hi - new_width / 2 + 1e-6


def test_suppressed_override_removes_only_that_opening():
    base = build_floor_drawing(_fp(), _cfg())
    win = _window(base)
    n = len(base.openings)
    out = build_floor_drawing(
        _fp([OpeningOverride(opening_id=win.id, suppressed=True)]), _cfg()
    )
    assert len(out.openings) == n - 1
    assert all(o.id != win.id for o in out.openings)


def test_unknown_opening_id_drops_silently_with_diagnostic():
    base = build_floor_drawing(_fp(), _cfg())
    out = build_floor_drawing(
        _fp([OpeningOverride(opening_id="w:v:i:ghost@9.99:0.00-0.00#0.000")]), _cfg()
    )
    assert [o.id for o in out.openings] == [o.id for o in base.openings]
    assert any("ghost" in d for d in out.diagnostics), out.diagnostics
    assert all("override" in d.lower() for d in out.diagnostics if "ghost" in d)


def test_override_outside_host_wall_is_rejected():
    base = build_floor_drawing(_fp(), _cfg())
    win = _window(base)
    wall, (lo, hi) = _wall_span(base, win)
    length = hi - lo
    out = build_floor_drawing(
        _fp([OpeningOverride(opening_id=win.id, along=length + 5.0)]), _cfg()
    )
    win2 = next(o for o in out.openings if o.id == win.id)
    assert (win2.cx, win2.cy, win2.width) == (win.cx, win.cy, win.width)
    assert any(win.id in d and "outside" in d for d in out.diagnostics), out.diagnostics


def test_overrides_survive_rederivation_and_store_round_trip():
    base = build_floor_drawing(_fp(), _cfg())
    win = _window(base)
    _, (lo, hi) = _wall_span(base, win)
    overrides = [OpeningOverride(opening_id=win.id, along=(hi - lo) / 3)]
    fp = _fp(overrides)
    d1 = build_floor_drawing(fp, _cfg())
    d2 = build_floor_drawing(fp, _cfg())
    assert d1.to_dict() == d2.to_dict()

    # persistence: LayoutOut.model_dump -> StoredLayout.geometry -> engine
    from tests.helpers.golden import golden_layout

    lay = golden_layout()
    lay.ground_floor.opening_overrides = [
        OpeningOverride(opening_id=win.id, along=(hi - lo) / 3, width=0.75)
    ]
    geometry = layout_out_from_engine(lay).model_dump()
    rehydrated = engine_layout_from_geometry(geometry)
    assert (
        rehydrated.ground_floor.opening_overrides == lay.ground_floor.opening_overrides
    )


def test_floorplan_without_overrides_still_deserialises():
    """Global constraint: every new field is optional with a default."""
    assert _fp().opening_overrides == []
    fp = FloorPlan(floor=0, rooms=_rooms())  # field not passed at all
    assert fp.opening_overrides == []
    drawing = build_floor_drawing(fp, _cfg())
    assert drawing.openings


def test_override_only_edit_changes_geometry_hash():
    """A moved window is a real drawing change: an override-only edit must
    not hash identical to the approved revision it departs from."""
    from app.services.structural_store import geometry_hash

    def _geom(with_override: bool) -> dict:
        lay = layout_out_from_engine(_layout_with_override()).model_dump()
        if with_override:
            lay["ground_floor"]["opening_overrides"] = [
                {"opening_id": "some-opening", "along": 1.2, "width": 0.9}
            ]
        return lay

    from tests.helpers.golden import golden_layout

    def _layout_with_override():
        return golden_layout()

    base = geometry_hash(_geom(False))
    moved = geometry_hash(_geom(True))
    assert base != moved
