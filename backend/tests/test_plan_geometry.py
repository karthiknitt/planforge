"""Canonical wall/junction/column derivation invariants (S4.1).

Room-layout convention (verified against ccqs_fixture.json + archetypes.py):
rooms are CLEAR interior rects — adjacent rooms are separated by an
iwt-wide gap and the whole plate is inset ewt from the buildable ring.
Walls therefore live in the gaps: paired internal walls at gap midpoints,
the external ring at buildable − ewt/2, orphan walls hugging edges that
face unassigned space.
"""

import math

import pytest
from shapely.geometry import box

from app.engine.cad_elements import WallJunction
from app.engine.geometry import buildable_polygon
from app.engine.models import PlotConfig, Room
from app.engine.plan_geometry import (
    _SNAP,
    _merge_adjacent_columns,
    _near_staircase,
    _plate_bounds,
    _structural_rooms,
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
    # b's top edge at y=7.73 faces open sky (interior void, inside the
    # room-union bbox since "a" extends further back) → external (ewt) wall
    # centred ewt/2 above it, not internal (#75)
    orphan = [
        w
        for w in walls
        if not _seg_is_vertical(w) and abs(w.y1 - (7.73 + EWT / 2)) < 1e-6
    ]
    assert len(orphan) == 1
    assert orphan[0].kind == "external"
    assert orphan[0].thickness == pytest.approx(EWT)
    lo, hi = _interval(orphan[0])
    assert lo >= 4.0 and hi <= 7.885 + 1e-6


def test_interior_void_facing_edge_is_external():
    """#75: a room edge facing an interior void — inside the room-union
    bbox, not on its boundary — is structurally exterior (open to sky) and
    must get an `external`/ewt orphan wall, not `internal`/iwt.

    "living" is deeper than "stair", so the bbox rear (7.73, living's own
    rear edge) is further back than stair's rear edge (5.73). Stair's rear
    edge is therefore uncovered by both the ring (not on the bbox boundary)
    and edge-pairing (nothing faces it) — it opens onto the void beside
    living's extra depth, a genuine interior void.
    """
    cfg = _cfg_9x15()
    rooms = [
        _room("living", 1.23, 1.73, 4.0, 6.0),  # rear at y=7.73 (defines bbox rear)
        _room("stair", 5.23, 1.73, 2.0, 4.0, rtype="staircase"),  # rear at y=5.73
    ]
    walls = derive_walls(rooms, buildable_polygon(cfg))
    void_facing = [
        w
        for w in walls
        if not _seg_is_vertical(w) and abs(w.y1 - (5.73 + EWT / 2)) < 1e-6
    ]
    assert void_facing, "expected an orphan wall on stair's void-facing rear edge"
    for w in void_facing:
        assert w.kind == "external"
        assert w.thickness == pytest.approx(EWT)


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
        _room("b", mid + IWT / 2, py1, px2 - (mid + IWT / 2), front_depth),
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
    # Ring-touching or genuinely span-critical Ts may still remain among
    # `kept`; the len() check above already confirms at least one was pruned.
    assert kept.issubset({(round(j.x, 3), round(j.y, 3)) for j in junctions})


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


def test_near_staircase_detects_points_on_and_off_a_staircase_footprint():
    stair = Room(
        id="stair", name="stair", type="staircase", x=1.0, y=1.0, width=2.0, depth=2.0
    )
    rooms = [stair]
    # inside the footprint
    assert _near_staircase(2.0, 2.0, rooms) is True
    # just outside, within the default 0.3 m tol
    assert _near_staircase(3.2, 2.0, rooms) is True
    # well outside the tol
    assert _near_staircase(5.0, 2.0, rooms) is False
    # no rooms at all
    assert _near_staircase(2.0, 2.0, None) is False
    assert _near_staircase(2.0, 2.0, []) is False
    # non-staircase rooms are never a match
    bedroom = Room(
        id="bed", name="bed", type="bedroom", x=1.0, y=1.0, width=2.0, depth=2.0
    )
    assert _near_staircase(2.0, 2.0, [bedroom]) is False


def test_columns_merge_when_staircase_wall_and_neighbour_wall_are_close():
    # Two "certain" junctions 0.9 m apart — too far for the general 0.3 m
    # dedup, close enough that leaving both in reads as a structurally
    # implausible grid once one of them abuts a staircase core.
    stair = Room(
        id="stair", name="stair", type="staircase", x=0.0, y=0.0, width=2.0, depth=2.0
    )
    j_stair = WallJunction(x=1.9, y=1.0, degree=4)  # inside the staircase footprint
    j_other = WallJunction(x=2.8, y=1.0, degree=3)  # 0.9 m away, outside it

    merged = _merge_adjacent_columns([j_stair, j_other], rooms=[stair])
    assert len(merged) == 1, (
        "staircase-adjacent close pair should collapse to one column"
    )
    kept = (round(merged[0].cx, 3), round(merged[0].cy, 3))
    assert kept == (1.9, 1.0), (
        "the higher-degree (better-anchored) junction should survive"
    )


def test_columns_not_merged_when_close_pair_is_not_staircase_adjacent():
    # Identical 0.9 m spacing, but neither junction is near a staircase —
    # the widened radius must NOT kick in here; both columns must survive.
    j_a = WallJunction(x=1.9, y=1.0, degree=4)
    j_b = WallJunction(x=2.8, y=1.0, degree=3)

    merged_no_rooms = _merge_adjacent_columns([j_a, j_b], rooms=None)
    assert len(merged_no_rooms) == 2, "unrelated close junctions must not be merged"

    bedroom = Room(
        id="bed", name="bed", type="bedroom", x=0.0, y=0.0, width=2.0, depth=2.0
    )
    merged_with_bedroom = _merge_adjacent_columns([j_a, j_b], rooms=[bedroom])
    assert len(merged_with_bedroom) == 2, (
        "a non-staircase room nearby must not trigger the widened merge radius"
    )


def test_derive_columns_rooms_param_optional_backward_compatible():
    cfg = _cfg_9x15()
    rooms = _two_full_height_rooms()
    walls = derive_walls(rooms, buildable_polygon(cfg))
    junctions = derive_junctions(walls)

    without_rooms = derive_columns(walls, junctions=junctions)
    with_none = derive_columns(walls, junctions=junctions, rooms=None)
    assert [(round(c.cx, 3), round(c.cy, 3)) for c in without_rooms] == [
        (round(c.cx, 3), round(c.cy, 3)) for c in with_none
    ]


def test_external_ring_follows_room_union_not_buildable():
    # rooms cover only the FRONT half of the _cfg_9x15 plate — roof void at rear
    rooms = [
        _room("living", 1.23, 1.73, 4.0, 4.0),
        _room("stair", 5.23, 1.73, 2.0, 4.0, rtype="staircase"),
    ]
    buildable = buildable_polygon(_cfg_9x15())
    walls = derive_walls(rooms, buildable)
    ext = [w for w in walls if w.kind == "external"]
    rear_cyt = max(max(w.y1, w.y2) for w in ext)
    front_cyb = min(min(w.y1, w.y2) for w in ext)
    # ring hugs the room union (5.73 + EWT/2), NOT the buildable rear edge
    assert rear_cyt == pytest.approx(5.73 + EWT / 2, abs=1e-6)
    assert front_cyb == pytest.approx(1.73 - EWT / 2, abs=1e-6)
    # full set of four external centrelines: right hugged at 7.23 + EWT/2 too
    coords = sorted(w.x1 if _seg_is_vertical(w) else w.y1 for w in ext)
    assert coords == pytest.approx([1.115, 1.615, 5.845, 7.345], abs=1e-6)


def test_external_ring_falls_back_to_buildable_without_rooms():
    buildable = buildable_polygon(_cfg_9x15())
    walls = derive_walls([], buildable)
    ext = [w for w in walls if w.kind == "external"]
    assert len(ext) == 4
    coords = sorted(w.x1 if _seg_is_vertical(w) else w.y1 for w in ext)
    assert coords == pytest.approx([1.115, 1.615, 7.885, 13.885], abs=1e-6)


def test_external_ring_leaves_notch_open_no_false_wall():
    """#6c follow-up: an L-shaped footprint (a full-width front row plus a
    rear row that only covers PART of the width -- e.g. a floor with a
    sloped-roof void over one rear corner, as seen on the Assamese-07
    reverse-engineering reconstruction) must not get a false wall ring
    closing off the empty notch. `_plate_bounds` still reports the room
    union's bbox (which includes the notch), but each ring side must only
    be built from the room edges that actually reach it -- the old
    unconditional full-bbox-side ring drew a wall across the notch even
    though no room, and therefore no real building fabric, is there."""
    rooms = [
        # full-width front row: x[1.23, 7.77] y[1.73, 7.73]
        _room("living", 1.23, 1.73, 6.54, 6.0),
        # rear row covers only the WEST half: x[1.23, 4.0] y[7.73, 13.77]
        # -- notch (no room) at x[4.0, 7.77] y[7.73, 13.77]
        _room("bedroom", 1.23, 7.73, 2.77, 6.04),
    ]
    buildable = buildable_polygon(_cfg_9x15())
    walls = derive_walls(rooms, buildable)
    ext = [w for w in walls if w.kind == "external"]

    # North ring (rear, y ~ 13.885) must stop at bedroom's own east edge
    # (x=4.0), not reach all the way to the buildable-derived east
    # centreline (7.885) the way the old bbox-side ring did.
    north = [w for w in ext if not _seg_is_vertical(w) and w.y1 > 10.0]
    assert north, "expected a north ring wall over bedroom"
    assert max(max(w.x1, w.x2) for w in north) < 4.0 + _SNAP + 1e-6

    # East ring (right side, x ~ 7.885) must stop at living's own rear edge
    # (y=7.73), not reach up to the buildable-derived north centreline
    # (13.885) the way the old bbox-side ring did.
    east = [w for w in ext if _seg_is_vertical(w) and w.x1 > 6.0]
    assert east, "expected an east ring wall alongside living"
    assert max(max(w.y1, w.y2) for w in east) < 7.73 + _SNAP + 1e-6

    # No external wall segment should have an endpoint inside the notch's
    # far corner region at all.
    for w in ext:
        for x, y in ((w.x1, w.y1), (w.x2, w.y2)):
            assert not (x > 5.0 and y > 10.0), f"false wall in notch corner: {w}"


# --- Room.open_sides: walls omitted on declared-open edges -----------------


def _buildable():
    return box(0, 0, 12, 12)


def _walls_on_edge(walls, *, vertical: bool, coord: float, tol: float = 0.12):
    """WallSegments whose centreline sits on x=coord (vertical) or y=coord.

    `tol` must exceed EWT/2 (0.115): a room edge on the plate boundary is
    walled by the external ring, whose centreline sits ewt/2 *outside* the
    edge (a room at y=0 gets its south wall at y=-0.115). Room edges in
    these fixtures are metres apart, so 0.12 is still unambiguous.
    """
    out = []
    for w in walls:
        is_v = abs(w.x1 - w.x2) < 1e-6
        if is_v != vertical:
            continue
        c = w.x1 if is_v else w.y1
        if abs(c - coord) <= tol:
            out.append(w)
    return out


def test_open_side_gets_no_wall():
    """A car porch open on its road-facing (S) edge gets no wall there,
    but keeps its other three walls."""
    porch = Room(
        id="porch",
        name="Car Porch",
        type="parking_4w",
        x=1.0,
        y=0.0,
        width=3.0,
        depth=5.0,
        open_sides=frozenset({"S"}),
    )
    walls = derive_walls([porch], _buildable())
    assert _walls_on_edge(walls, vertical=False, coord=0.0) == []
    assert _walls_on_edge(walls, vertical=False, coord=5.0), "N wall must remain"
    assert _walls_on_edge(walls, vertical=True, coord=1.0), "W wall must remain"
    assert _walls_on_edge(walls, vertical=True, coord=4.0), "E wall must remain"


def test_closed_room_unchanged_by_the_feature():
    """Regression: a room with no open_sides derives exactly the walls it
    derived before this feature existed — all four edges present."""
    r = Room(id="r", name="Living", type="living", x=1.0, y=1.0, width=4.0, depth=3.0)
    walls = derive_walls([r], _buildable())
    for vertical, coord in ((False, 1.0), (False, 4.0), (True, 1.0), (True, 5.0)):
        assert _walls_on_edge(walls, vertical=vertical, coord=coord), (
            f"missing wall at {'x' if vertical else 'y'}={coord}"
        )


def test_party_wall_survives_neighbour_declaring_open():
    """A porch open on its N edge that abuts a living room must NOT delete the
    living room's S wall — the shared wall is still real."""
    porch = Room(
        id="porch",
        name="Car Porch",
        type="parking_4w",
        x=1.0,
        y=0.0,
        width=3.0,
        depth=5.0,
        open_sides=frozenset({"N"}),
    )
    living = Room(
        id="living",
        name="Living",
        type="living",
        x=1.0,
        y=5.0,
        width=3.0,
        depth=4.0,
    )
    walls = derive_walls([porch, living], _buildable())
    assert _walls_on_edge(walls, vertical=False, coord=5.0), (
        "shared porch/living wall was wrongly deleted"
    )


def test_party_wall_survives_two_neighbours_declaring_open():
    """Horizontal party wall shared by TWO non-open rooms.

    The wall the pairing pass builds is a single merged segment spanning both
    neighbours, so the rescue must see the neighbours' south edges as one
    merged run too — matching each raw per-room edge on its own never
    contains the merged wall, and the wall gets dropped. Note both
    neighbours here have EMPTY open_sides: they must not lose a wall
    because some *other* room declared itself open.
    """
    porch = Room(
        id="porch",
        name="Car Porch",
        type="parking_4w",
        x=1.0,
        y=0.0,
        width=4.0,
        depth=5.0,
        open_sides=frozenset({"N"}),
    )
    living = Room(
        id="living", name="Living", type="living", x=1.0, y=5.0, width=2.0, depth=4.0
    )
    kitchen = Room(
        id="kitchen", name="Kitchen", type="kitchen", x=3.0, y=5.0, width=2.0, depth=4.0
    )
    rooms = [porch, living, kitchen]
    walls = derive_walls(rooms, _buildable())
    assert _walls_on_edge(walls, vertical=False, coord=5.0), (
        "party wall shared by two non-open neighbours was wrongly deleted"
    )
    # ...and the feature is still a no-op for the closed rooms: the same
    # layout with nothing declared open derives the same wall count.
    closed = derive_walls(
        [
            Room(
                id="porch",
                name="Car Porch",
                type="parking_4w",
                x=1.0,
                y=0.0,
                width=4.0,
                depth=5.0,
            ),
            living,
            kitchen,
        ],
        _buildable(),
    )
    assert len(walls) == len(closed)


def test_vertical_party_wall_survives_two_neighbours_declaring_open():
    """Same multi-neighbour rescue on the VERTICAL axis.

    Guards the covered_v/covered_h split: a porch open on its E edge abutting
    two stacked rooms must not delete their shared W wall.
    """
    porch = Room(
        id="porch",
        name="Car Porch",
        type="parking_4w",
        x=0.0,
        y=0.0,
        width=3.0,
        depth=6.0,
        open_sides=frozenset({"E"}),
    )
    r1 = Room(id="r1", name="Bed 1", type="bedroom", x=3.0, y=0.0, width=4.0, depth=3.0)
    r2 = Room(id="r2", name="Bed 2", type="bedroom", x=3.0, y=3.0, width=4.0, depth=3.0)
    walls = derive_walls([porch, r1, r2], _buildable())
    assert _walls_on_edge(walls, vertical=True, coord=3.0), (
        "vertical party wall shared by two non-open neighbours was deleted"
    )


def test_perpendicular_edge_does_not_rescue_an_open_wall():
    """The party-wall rescue must not match across axes.

    A corner porch open to the road on S: its south wall's centreline is
    y=-0.115 and the wall spans x=[-0.115, 3.115]. The porch's OWN west edge
    is the vertical line x=0.0 spanning y=[0, 5] — numerically close enough
    to -0.115, and wide enough to contain the span, that an orientation-blind
    `covered` set rescues the very wall the porch declared open. Keeping the
    covered edges split by axis is what prevents that.
    """
    porch = Room(
        id="porch",
        name="Car Porch",
        type="parking_4w",
        x=0.0,
        y=0.0,
        width=3.0,
        depth=5.0,
        open_sides=frozenset({"S"}),
    )
    walls = derive_walls([porch], _buildable())
    assert _walls_on_edge(walls, vertical=False, coord=0.0) == [], (
        "S wall survived: a perpendicular (vertical) edge wrongly rescued it"
    )
    assert _walls_on_edge(walls, vertical=True, coord=0.0), "W wall must remain"


# --- carved / nested rooms (Room.parent_id) ---------------------------------


def _carve_pair() -> tuple[Room, Room]:
    """A 4x4 bedroom with a 1.5x2.0 toilet carved into its SW corner."""
    bedroom = Room(
        id="bed",
        name="Bedroom",
        type="bedroom",
        x=1.0,
        y=1.0,
        width=4.0,
        depth=4.0,
    )
    toilet = Room(
        id="wc",
        name="Toilet",
        type="toilet",
        x=1.0,
        y=1.0,
        width=1.5,
        depth=2.0,
        parent_id="bed",
    )
    return bedroom, toilet


def test_carved_room_does_not_duplicate_parent_walls():
    """A toilet carved into a bedroom's rectangle gets its own two internal
    separating walls, and the bedroom keeps all four of its own outer walls —
    the carve must not punch a hole in the parent's envelope."""
    bedroom, toilet = _carve_pair()
    walls = derive_walls([bedroom, toilet], _buildable())
    # Parent envelope intact on all four sides.
    for vertical, coord in ((False, 1.0), (False, 5.0), (True, 1.0), (True, 5.0)):
        assert _walls_on_edge(walls, vertical=vertical, coord=coord), (
            f"parent lost its wall at {'x' if vertical else 'y'}={coord}"
        )
    # Carve produces the two interior separating walls (x=2.5 and y=3.0).
    assert _walls_on_edge(walls, vertical=True, coord=2.5), "missing carve E wall"
    assert _walls_on_edge(walls, vertical=False, coord=3.0), "missing carve N wall"


def test_carve_separating_walls_are_internal_not_exterior():
    """The carve's own edges face the parent's mass, so they must read as
    interior partitions (iwt) — never as void-facing external surfaces."""
    bedroom, toilet = _carve_pair()
    walls = derive_walls([bedroom, toilet], _buildable())
    for vertical, coord in ((True, 2.5), (False, 3.0)):
        segs = _walls_on_edge(walls, vertical=vertical, coord=coord)
        assert segs, f"no wall at {'x' if vertical else 'y'}={coord}"
        assert all(w.kind == "internal" for w in segs), (
            f"carve wall at {'x' if vertical else 'y'}={coord} is not internal: "
            f"{[(w.kind, w.thickness) for w in segs]}"
        )
        assert all(abs(w.thickness - IWT) < 1e-9 for w in segs)


def test_carved_child_excluded_from_parent_net_area():
    bedroom, toilet = _carve_pair()
    assert bedroom.area == 16.0
    assert bedroom.net_area([toilet]) == 13.0
    # An unrelated room never reduces the parent's net area.
    other = Room(
        id="oth", name="Store", type="store_room", x=20.0, y=20.0, width=2.0, depth=2.0
    )
    assert bedroom.net_area([other]) == 16.0
    # No children at all -> net area equals gross area (default behaviour).
    assert bedroom.net_area([]) == bedroom.area


def test_carve_must_lie_inside_its_parent():
    bedroom, _ = _carve_pair()
    stray = Room(
        id="wc",
        name="Toilet",
        type="toilet",
        x=9.0,
        y=9.0,
        width=1.5,
        depth=2.0,
        parent_id="bed",
    )
    with pytest.raises(ValueError, match="not contained"):
        derive_walls([bedroom, stray], _buildable())


def test_carve_with_unknown_parent_is_rejected():
    bedroom, _ = _carve_pair()
    orphan = Room(
        id="wc",
        name="Toilet",
        type="toilet",
        x=1.0,
        y=1.0,
        width=1.5,
        depth=2.0,
        parent_id="nope",
    )
    with pytest.raises(ValueError, match="unknown parent_id"):
        derive_walls([bedroom, orphan], _buildable())


# Golden wall set for the 6-room ground floor of the shared fixture, captured
# BEFORE `Room.parent_id` existed. Every entry is
# (x1, y1, x2, y2, thickness, kind), rounded to 4 dp and sorted.
_GOLDEN_GF_WALLS = [
    (1.115, 1.615, 1.115, 4.845, 0.23, "external"),
    (1.115, 1.615, 7.885, 1.615, 0.23, "external"),
    (1.115, 4.845, 2.1875, 4.845, 0.23, "external"),
    (1.115, 5.944, 1.115, 13.885, 0.23, "external"),
    (1.115, 5.944, 4.995, 5.944, 0.23, "external"),
    (1.115, 13.885, 7.885, 13.885, 0.23, "external"),
    (2.1875, 1.615, 2.1875, 4.845, 0.115, "internal"),
    (2.1875, 4.845, 4.995, 4.845, 0.23, "external"),
    (4.8845, 5.944, 4.8845, 13.885, 0.115, "internal"),
    (4.8845, 5.944, 5.0525, 5.944, 0.23, "external"),
    (4.8845, 6.0015, 6.9615, 6.0015, 0.115, "internal"),
    (4.995, 4.7875, 4.995, 5.944, 0.23, "external"),
    (5.0525, 1.615, 5.0525, 4.845, 0.115, "internal"),
    (6.904, 6.0015, 7.019, 6.0015, 0.115, "internal"),
    (6.9615, 6.0015, 6.9615, 13.885, 0.115, "internal"),
    (6.9615, 6.0015, 7.885, 6.0015, 0.115, "internal"),
    (7.885, 1.615, 7.885, 13.885, 0.23, "external"),
]


def _wall_tuples(walls) -> list[tuple[float, float, float, float, float, str]]:
    return sorted(
        (
            round(w.x1, 4),
            round(w.y1, 4),
            round(w.x2, 4),
            round(w.y2, 4),
            round(w.thickness, 4),
            w.kind,
        )
        for w in walls
    )


def test_parent_id_defaults_to_none_and_changes_nothing():
    """The load-bearing invariant of the whole phase: with no `parent_id`
    anywhere, `derive_walls` must reproduce the pre-feature wall set exactly
    — same count, same centrelines, same thicknesses, same kinds."""
    rooms, cfg = golden_layout().ground_floor.rooms, golden_config()
    assert all(r.parent_id is None for r in rooms)
    walls = derive_walls(rooms, buildable_polygon(cfg))
    assert len(walls) == len(_GOLDEN_GF_WALLS)
    assert _wall_tuples(walls) == _GOLDEN_GF_WALLS


def test_room_is_its_own_parent_is_rejected():
    """Self-parent is trivially "contained", so only the cycle pass catches
    it — and unchecked it empties `_structural_rooms` and degrades the plate
    to the whole buildable inset."""
    bedroom, _ = _carve_pair()
    bedroom.parent_id = "bed"
    with pytest.raises(ValueError, match="parent_id cycle"):
        derive_walls([bedroom], _buildable())


def test_two_node_parent_id_cycle_is_rejected():
    a, b = _carve_pair()
    a.parent_id = "wc"  # bed -> wc -> bed
    with pytest.raises(ValueError, match="parent_id cycle") as exc:
        derive_walls([a, b], _buildable())
    assert "bed" in str(exc.value) and "wc" in str(exc.value)


def test_three_node_parent_id_cycle_is_rejected():
    a = Room(id="a", name="A", type="bedroom", x=1.0, y=1.0, width=4.0, depth=4.0)
    b = Room(id="b", name="B", type="toilet", x=1.0, y=1.0, width=2.0, depth=2.0)
    c = Room(id="c", name="C", type="store_room", x=1.0, y=1.0, width=1.0, depth=1.0)
    a.parent_id, b.parent_id, c.parent_id = "b", "c", "a"
    with pytest.raises(ValueError, match="parent_id cycle") as exc:
        derive_walls([a, b, c], _buildable())
    assert all(rid in str(exc.value) for rid in ("a", "b", "c"))


def test_cycle_would_otherwise_degrade_the_plate_to_the_buildable():
    """Pins WHY the cycle guard exists: without it, every room is filtered
    out as a carve and the plate silently falls back to the buildable ring.
    `_structural_rooms` alone still shows the degradation, so the guard in
    `derive_walls` is the only thing standing between that and a wall ring
    drawn around empty plot."""
    bedroom, toilet = _carve_pair()
    bedroom.parent_id = "wc"
    assert _structural_rooms([bedroom, toilet]) == []
    degraded = _plate_bounds([bedroom, toilet], _buildable(), EWT)
    assert degraded == pytest.approx((EWT, EWT, 12.0 - EWT, 12.0 - EWT))
    with pytest.raises(ValueError, match="parent_id cycle"):
        derive_walls([bedroom, toilet], _buildable())


def test_carve_within_containment_tolerance_does_not_inflate_the_plate():
    """`_validate_carves` allows 1 cm of slop, so a carve CAN stick marginally
    past its parent. It must still be filtered out of the footprint union, or
    that slop silently grows the plate the exterior ring is built on."""
    bedroom, _ = _carve_pair()
    sloppy = Room(
        id="wc",
        name="Toilet",
        type="toilet",
        x=1.0,
        y=1.0,
        width=4.01,  # 1 cm past the parent's E edge — inside the 0.01 tol
        depth=2.0,
        parent_id="bed",
    )
    assert _structural_rooms([bedroom, sloppy]) == [bedroom]
    derive_walls([bedroom, sloppy], _buildable())  # tolerated, not an error
    _px1, _py1, px2, _py2 = _plate_bounds([bedroom, sloppy], _buildable(), EWT)
    assert px2 == pytest.approx(5.0), (
        f"carve mass leaked into the plate: east bound {px2} != parent's 5.0"
    )
