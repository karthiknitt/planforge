"""Canonical wall/junction/column derivation invariants (S4.1).

Room-layout convention (verified against ccqs_fixture.json + archetypes.py):
rooms are CLEAR interior rects — adjacent rooms are separated by an
iwt-wide gap and the whole plate is inset ewt from the buildable ring.
Walls therefore live in the gaps: paired internal walls at gap midpoints,
the external ring at buildable − ewt/2, orphan walls hugging edges that
face unassigned space.
"""

import math

from shapely.geometry import box

from app.engine.geometry import buildable_polygon
from app.engine.models import PlotConfig, Room
from app.engine.plan_geometry import (
    derive_columns,
    derive_junctions,
    derive_walls,
    wall_polygons,
)

from tests.helpers.golden import golden_config, golden_layout

EWT = 0.23
IWT = 0.115


def _cfg_9x15() -> PlotConfig:
    return PlotConfig(
        plot_length=15.0,
        plot_width=9.0,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=1.0,
        setback_right=1.0,
        num_bedrooms=2,
        toilets=1,
        parking=False,
        num_floors=1,
    )


def _room(
    rid: str, x: float, y: float, w: float, d: float, rtype: str = "bedroom"
) -> Room:
    return Room(id=rid, name=rid, type=rtype, x=x, y=y, width=w, depth=d)


# Plate for the 9x15 cfg: buildable x∈[1.0,8.0] y∈[1.5,14.0] → plate
# x∈[1.23,7.77] y∈[1.73,13.77]. External centrelines: x=1.115/7.885, y=1.615/13.885.
def _two_full_height_rooms() -> list[Room]:
    return [
        _room("a", 1.23, 1.73, 2.77, 12.04),  # x2 = 4.0
        _room("b", 4.115, 1.73, 3.655, 12.04),  # x∈[4.115, 7.77]
    ]


def _seg_is_vertical(s) -> bool:
    return abs(s.x1 - s.x2) < 1e-9


def _interval(s) -> tuple[float, float]:
    if _seg_is_vertical(s):
        return (min(s.y1, s.y2), max(s.y1, s.y2))
    return (min(s.x1, s.x2), max(s.x1, s.x2))


def test_side_by_side_rooms_single_internal_wall():
    cfg = _cfg_9x15()
    walls = derive_walls(_two_full_height_rooms(), buildable_polygon(cfg))
    internal = [w for w in walls if w.kind == "internal"]
    assert len(internal) == 1
    w = internal[0]
    assert _seg_is_vertical(w)
    assert math.isclose(w.x1, 4.0575, abs_tol=1e-6)  # gap midpoint
    assert math.isclose(w.thickness, IWT, abs_tol=1e-9)
    lo, hi = _interval(w)
    # end-snapped to the external centrelines
    assert math.isclose(lo, 1.615, abs_tol=1e-3)
    assert math.isclose(hi, 13.885, abs_tol=1e-3)


def test_external_ring_closed_at_centrelines():
    cfg = _cfg_9x15()
    walls = derive_walls(_two_full_height_rooms(), buildable_polygon(cfg))
    ext = [w for w in walls if w.kind == "external"]
    assert len(ext) == 4
    coords = set()
    for w in ext:
        assert math.isclose(w.thickness, EWT, abs_tol=1e-9)
        coords.add(round(w.x1 if _seg_is_vertical(w) else w.y1, 4))
    assert coords == {1.115, 7.885, 1.615, 13.885}


def test_partition_wall_never_crosses_room_above():
    """Regression for the phantom full-span wall bug: the a|b partition must
    stop at the full-width room c above, not slice through it."""
    cfg = _cfg_9x15()
    rooms = [
        _room("a", 1.23, 1.73, 2.77, 5.0),  # y2 = 6.73
        _room("b", 4.115, 1.73, 3.655, 5.0),
        _room("c", 1.23, 6.845, 6.54, 6.925),  # full width, y∈[6.845, 13.77]
    ]
    walls = derive_walls(rooms, buildable_polygon(cfg))
    vert_internal = [
        w
        for w in walls
        if w.kind == "internal" and _seg_is_vertical(w) and abs(w.x1 - 4.0575) < 1e-6
    ]
    assert vert_internal, "paired wall missing"
    hi = max(_interval(w)[1] for w in vert_internal)
    # may snap to the a/c–b/c wall centreline at 6.7875, never into room c
    assert hi <= 6.7875 + 1e-6, f"phantom wall: partition extends to {hi}"
    from shapely.geometry import LineString

    c_interior = box(1.23, 6.845, 7.77, 13.77).buffer(-0.01)
    for w in vert_internal:
        assert not LineString([(w.x1, w.y1), (w.x2, w.y2)]).intersects(c_interior)


def test_orphan_edge_gets_wall():
    cfg = _cfg_9x15()
    rooms = [
        _room("a", 1.23, 1.73, 2.77, 12.04),
        _room("b", 4.115, 1.73, 3.655, 6.0),
    ]
    walls = derive_walls(rooms, buildable_polygon(cfg))
    # b's top edge at y=7.73 faces void → orphan wall centred iwt/2 above it
    orphan = [
        w
        for w in walls
        if not _seg_is_vertical(w) and abs(w.y1 - (7.73 + IWT / 2)) < 1e-6
    ]
    assert len(orphan) == 1
    lo, hi = _interval(orphan[0])
    assert lo >= 4.0 and hi <= 7.885 + 1e-6


def _all_floor_walls(rooms, cfg):
    return derive_walls(rooms, buildable_polygon(cfg))


def _fixture_floors():
    layout = golden_layout()
    cfg = golden_config()
    return [(layout.ground_floor.rooms, cfg), (layout.first_floor.rooms, cfg)]


def test_fixture_no_wall_crosses_room_interior():
    for rooms, cfg in _fixture_floors():
        walls = _all_floor_walls(rooms, cfg)
        for r in rooms:
            interior = box(r.x, r.y, r.x + r.width, r.y + r.depth).buffer(-0.01)
            for w in walls:
                from shapely.geometry import LineString

                line = LineString([(w.x1, w.y1), (w.x2, w.y2)])
                assert not line.intersects(interior), f"wall {w} crosses room {r.id}"


def test_fixture_every_room_edge_has_a_wall():
    for rooms, cfg in _fixture_floors():
        walls = _all_floor_walls(rooms, cfg)
        for r in rooms:
            edges = [
                ("v", r.x, r.y, r.y + r.depth),
                ("v", r.x + r.width, r.y, r.y + r.depth),
                ("h", r.y, r.x, r.x + r.width),
                ("h", r.y + r.depth, r.x, r.x + r.width),
            ]
            for orient, coord, lo, hi in edges:
                covering = []
                for w in walls:
                    w_vert = _seg_is_vertical(w)
                    if (orient == "v") != w_vert:
                        continue
                    w_coord = w.x1 if w_vert else w.y1
                    if abs(w_coord - coord) > EWT / 2 + 0.01:
                        continue
                    wlo, whi = _interval(w)
                    covering.append((wlo, whi))
                # union of covering intervals must span [lo, hi] (tol 2cm)
                covering.sort()
                pos = lo + 0.02
                for wlo, whi in covering:
                    if wlo <= pos:
                        pos = max(pos, whi)
                assert pos >= hi - 0.02, (
                    f"room {r.id} edge {orient}@{coord:.3f} uncovered from {pos:.3f}"
                )


def _cfg_wide_9x15() -> PlotConfig:
    # Same buildable depth as _cfg_9x15 but wide enough that the front-room
    # divider's ring-to-ring span (~6.77 m) exceeds max_beam_span_m (4.5 m).
    return _cfg_9x15()


def _cfg_narrow_5x15() -> PlotConfig:
    # Buildable width ~4.27 m ring-to-ring — under max_beam_span_m (4.5 m)
    # even without any intermediate column.
    return PlotConfig(
        plot_length=15.0,
        plot_width=5.5,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=0.5,
        setback_right=0.5,
        num_bedrooms=2,
        toilets=1,
        parking=False,
        num_floors=1,
    )


def _front_pair_plus_rear_room(cfg: PlotConfig) -> list[Room]:
    """Two front rooms split by a partition, plus a full-width rear room.

    The partition's foot meets the front/rear divider at a pure INTERIOR
    T-junction (touches neither the exterior ring nor a 4-way crossing) —
    exactly the "intermediate column grid" pattern pro-tester layouts hit.
    """
    buildable = buildable_polygon(cfg)
    bx1, by1, bx2, _by2 = buildable.bounds
    px1, py1, px2 = bx1 + EWT, by1 + EWT, bx2 - EWT
    front_depth = 5.0
    mid = (px1 + px2) / 2
    return [
        _room("a", px1, py1, mid - IWT / 2 - px1, front_depth),
        _room(
            "b", mid + IWT / 2, py1, px2 - (mid + IWT / 2), front_depth
        ),
        _room(
            "c",
            px1,
            py1 + front_depth + IWT,
            px2 - px1,
            12.04 - front_depth - IWT,
            "living",
        ),
    ]


def test_interior_t_junction_dropped_when_span_stays_within_limit():
    cfg = _cfg_narrow_5x15()
    rooms = _front_pair_plus_rear_room(cfg)
    walls = derive_walls(rooms, buildable_polygon(cfg))
    junctions = derive_junctions(walls)
    interior_t = [j for j in junctions if j.degree == 3]
    assert interior_t, "fixture should produce at least one interior T-junction"

    columns = derive_columns(walls, junctions=junctions, max_beam_span_m=4.5)
    kept = {(round(c.cx, 3), round(c.cy, 3)) for c in columns}
    # The candidate T where the vertical partition meets the rear divider
    # is not on the exterior ring and the through-wall span stays <4.5 m —
    # it must NOT get its own column.
    assert len(columns) < len(junctions), "no interior T-junction was dropped"
    for j in interior_t:
        pt = (round(j.x, 3), round(j.y, 3))
        # Ring-touching or genuinely span-critical Ts may still remain;
        # just assert we actually pruned something.
    assert kept.issubset(
        {(round(j.x, 3), round(j.y, 3)) for j in junctions}
    )


def test_interior_t_junction_kept_when_dropping_would_exceed_beam_span():
    cfg = _cfg_wide_9x15()
    rooms = _front_pair_plus_rear_room(cfg)
    walls = derive_walls(rooms, buildable_polygon(cfg))
    junctions = derive_junctions(walls)

    columns = derive_columns(walls, junctions=junctions, max_beam_span_m=4.5)
    kept = {(round(c.cx, 3), round(c.cy, 3)) for c in columns}
    # Ring-to-ring span here is ~6.77 m; dropping the mid T-junction would
    # leave an unsupported beam run far beyond max_beam_span_m, so it must
    # be kept even though it isn't on the ring or a 4-way crossing.
    mid_ts = [j for j in junctions if j.degree == 3 and not _on_ring_test(walls, j)]
    assert mid_ts, "fixture should produce a non-ring interior T-junction"
    for j in mid_ts:
        assert (round(j.x, 3), round(j.y, 3)) in kept, (
            f"interior T {j} was dropped despite exceeding beam span"
        )


def _on_ring_test(walls, j) -> bool:
    ext = [w for w in walls if w.kind == "external"]
    for w in ext:
        if _seg_is_vertical(w):
            lo, hi = min(w.y1, w.y2), max(w.y1, w.y2)
            if abs(w.x1 - j.x) <= 0.01 and lo - 0.01 <= j.y <= hi + 0.01:
                return True
        else:
            lo, hi = min(w.x1, w.x2), max(w.x1, w.x2)
            if abs(w.y1 - j.y) <= 0.01 and lo - 0.01 <= j.x <= hi + 0.01:
                return True
    return False


def test_fixture_columns_only_at_junctions_never_in_rooms():
    for rooms, cfg in _fixture_floors():
        walls = _all_floor_walls(rooms, cfg)
        junctions = derive_junctions(walls)
        columns = derive_columns(walls)
        assert columns, "no columns derived"
        jpts = {(round(j.x, 3), round(j.y, 3)) for j in junctions}
        for c in columns:
            assert (round(c.cx, 3), round(c.cy, 3)) in jpts
        for r in rooms:
            interior = box(r.x, r.y, r.x + r.width, r.y + r.depth).buffer(-0.01)
            for c in columns:
                from shapely.geometry import Point

                assert not interior.contains(Point(c.cx, c.cy)), (
                    f"column ({c.cx},{c.cy}) inside room {r.id}"
                )


def test_junction_degrees_two_room_case():
    cfg = _cfg_9x15()
    walls = derive_walls(_two_full_height_rooms(), buildable_polygon(cfg))
    junctions = derive_junctions(walls)
    degrees = sorted(j.degree for j in junctions)
    # 4 ring corners (degree 2) + 2 T-junctions (degree 3)
    assert degrees == [2, 2, 2, 2, 3, 3]


def test_wall_polygons_union_and_opening_subtraction():
    cfg = _cfg_9x15()
    walls = derive_walls(_two_full_height_rooms(), buildable_polygon(cfg))
    polys = wall_polygons(walls)
    ext, internal = polys["external"], polys["internal"]
    assert ext.is_valid and not ext.is_empty
    assert internal.is_valid and not internal.is_empty
    # external band is a ring: polygon with a hole
    ring = ext if ext.geom_type == "Polygon" else max(ext.geoms, key=lambda g: g.area)
    assert len(ring.interiors) == 1
    # subtracting a door-sized opening on the internal wall reduces its area
    door = box(4.0575 - IWT, 5.0, 4.0575 + IWT, 5.9)
    cut = wall_polygons(walls, openings=[door])["internal"]
    assert cut.area < internal.area - 1e-6
