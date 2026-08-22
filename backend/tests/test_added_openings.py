"""Added openings (Phase 7 / Task 30 engine half).

`OpeningOverride` can only delta ONE already-derived opening, so a user/AI
request for a NEW door or window needs an additive entity: `AddedOpening`,
carried on FloorPlan and resolved inside build_floor_drawing() BEFORE
assign_opening_ids()/assign_opening_marks() — added openings receive
identity and schedule marks through the same deterministic passes as
derived ones, and overrides may then target them. A spec whose rooms no
longer share a wall degrades to a diagnostic no-op, matching the Task 9 /
Task 29 tolerance principle.
"""

import pytest

from app.engine.models import AddedOpening, FloorPlan, OpeningOverride, PlotConfig
from app.engine.plan_geometry import build_floor_drawing, shared_wall_span
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


def _fp(
    added: list[AddedOpening] | None = None,
    overrides: list[OpeningOverride] | None = None,
) -> FloorPlan:
    return FloorPlan(
        floor=0,
        floor_type="ground",
        rooms=_rooms(),
        opening_overrides=overrides or [],
        added_openings=added or [],
    )


def test_shared_wall_span_finds_centreline_and_overlap():
    a, b, _, _ = _rooms()
    span = shared_wall_span(a, b)
    assert span is not None
    vertical, centre, lo, hi = span
    assert vertical is True
    assert centre == 4.4425  # midpoint of a.x2=4.385 / b.x1=4.5 (IWT=0.115)
    assert (lo, hi) == (7.73, 13.77)  # full-depth overlap


def test_shared_wall_span_returns_none_for_diagonal_rooms():
    a, _, _, d = _rooms()
    assert shared_wall_span(a, d) is None


def test_added_door_lands_on_shared_wall_centred_by_default():
    base = build_floor_drawing(_fp(), _cfg())
    out = build_floor_drawing(
        _fp(added=[AddedOpening(kind="door", room_a="c", room_b="d")]), _cfg()
    )
    assert len(out.openings) == len(base.openings) + 1
    door = next(o for o in out.openings if o.id.startswith("w:v:i:c>d@"))
    assert door.cx == 4.4425  # on the shared wall centreline
    assert door.cy == pytest.approx((1.73 + 7.615) / 2)  # span centre
    assert door.width == 0.9  # door default
    assert door.is_horizontal is False
    assert door.wall_thickness == 0.115  # internal wall
    assert door.swing_into_room_id == "d"
    assert door.id  # assigned through the usual id pass
    assert door.mark.startswith("D")  # and the mark pass


def test_added_door_respects_along_and_width():
    out = build_floor_drawing(
        _fp(
            added=[
                AddedOpening(kind="door", room_a="c", room_b="d", along=2.0, width=1.0)
            ]
        ),
        _cfg(),
    )
    door = next(o for o in out.openings if o.id.startswith("w:v:i:c>d@"))
    assert door.cy == 1.73 + 2.0  # along is measured from the span low end
    assert door.width == 1.0


def test_added_door_receives_id_targetable_by_overrides():
    """Placed before the id pass, so an override can move an added door."""
    spec = AddedOpening(kind="door", room_a="c", room_b="d")
    first = build_floor_drawing(_fp(added=[spec]), _cfg())
    door = next(o for o in first.openings if o.id.startswith("w:v:i:c>d@"))
    moved = build_floor_drawing(
        _fp(added=[spec], overrides=[OpeningOverride(opening_id=door.id, along=1.2)]),
        _cfg(),
    )
    door2 = next(o for o in moved.openings if o.id == door.id)
    # override `along` is measured from the host WALL's low end (the wall
    # segment outruns the room edge: 1.6725 vs 1.73): assert via the wall.
    wall = next(w for w in moved.walls if w.id == door.id.split("#")[0])
    wall_lo = min(wall.y1, wall.y2)
    assert door2.cy == wall_lo + 1.2


def test_added_door_degrades_when_rooms_share_no_wall():
    base = build_floor_drawing(_fp(), _cfg())
    out = build_floor_drawing(
        _fp(added=[AddedOpening(kind="door", room_a="a", room_b="d")]), _cfg()
    )
    assert [o.id for o in out.openings] == [o.id for o in base.openings]
    assert any("added_opening" in d and "'d'" in d for d in out.diagnostics)


def test_added_door_degrades_on_unknown_room():
    base = build_floor_drawing(_fp(), _cfg())
    out = build_floor_drawing(
        _fp(added=[AddedOpening(kind="door", room_a="a", room_b="ghost")]), _cfg()
    )
    assert [o.id for o in out.openings] == [o.id for o in base.openings]
    assert any("added_opening" in d and "ghost" in d for d in out.diagnostics)


def test_added_door_outside_on_chosen_side():
    # along=2.67 → cx 3.9: inside the edge (cx ≤ 4.385−0.45), 1.092 clear of
    # the derived window (centre 2.808) and 1.25 clear of the MD (centre 5.15).
    out = build_floor_drawing(
        _fp(
            added=[
                AddedOpening(
                    kind="door", room_a="c", room_b="outside", side="S", along=2.67
                )
            ]
        ),
        _cfg(),
    )
    door = next(
        o
        for o in out.openings
        if o.kind == "door" and o.id.startswith("w:h:e:->c+d@") and not o.is_main
    )
    assert door.is_horizontal is True
    assert door.cx == pytest.approx(3.9)
    assert door.cy == 1.615  # external wall centreline
    assert door.wall_thickness == 0.23
    assert door.swing_into_room_id == "c"
    assert door.mark.startswith("D")


def test_added_window_outside_picks_deterministic_edge_without_side():
    """Room a's free edges are W and N; the stable side order S,W,N,E picks
    W. `along` dodges the derived windows at span-centre."""
    out = build_floor_drawing(
        _fp(
            added=[AddedOpening(kind="window", room_a="a", room_b="outside", along=4.5)]
        ),
        _cfg(),
    )
    win = next(
        o
        for o in out.openings
        if o.kind == "window" and o.cx == 1.115 and abs(o.cy - 12.23) < 1e-9
    )
    assert win.width == 1.2  # window default
    assert win.is_horizontal is False
    assert win.wall_thickness == 0.23
    assert win.id.startswith("w:v:e:->a+c@")


def test_added_opening_rejected_when_off_span():
    base = build_floor_drawing(_fp(), _cfg())
    out = build_floor_drawing(
        _fp(added=[AddedOpening(kind="door", room_a="c", room_b="d", along=99.0)]),
        _cfg(),
    )
    assert [o.id for o in out.openings] == [o.id for o in base.openings]
    assert any("added_opening" in d for d in out.diagnostics)


def test_added_opening_rejected_when_it_overlaps_an_existing_one():
    """Span-centre defaults collide with derive's span-centred windows."""
    base = build_floor_drawing(_fp(), _cfg())
    out = build_floor_drawing(
        _fp(
            added=[AddedOpening(kind="window", room_a="a", room_b="outside", side="W")]
        ),
        _cfg(),
    )
    assert [o.id for o in out.openings] == [o.id for o in base.openings]
    assert any("added_opening" in d for d in out.diagnostics)


def test_added_openings_survive_store_round_trip():
    from tests.helpers.golden import golden_layout

    lay = golden_layout()
    added = [AddedOpening(kind="door", room_a="c", room_b="d", along=2.0, width=0.9)]
    lay.ground_floor.added_openings = added
    geometry = layout_out_from_engine(lay).model_dump()
    rehydrated = engine_layout_from_geometry(geometry)
    assert rehydrated.ground_floor.added_openings == added


def test_floorplan_without_added_openings_deserialises_and_draws_identically():
    """Global constraint: the new field is optional with a default, and an
    empty list must not perturb the derived drawing."""
    assert _fp().added_openings == []
    fp_bare = FloorPlan(floor=0, floor_type="ground", rooms=_rooms())
    assert fp_bare.added_openings == []
    assert (
        build_floor_drawing(_fp(), _cfg()).to_dict()
        == build_floor_drawing(fp_bare, _cfg()).to_dict()
    )


def test_build_stays_deterministic_with_added_openings():
    fp = _fp(added=[AddedOpening(kind="door", room_a="c", room_b="d")])
    assert (
        build_floor_drawing(fp, _cfg()).to_dict()
        == build_floor_drawing(fp, _cfg()).to_dict()
    )
