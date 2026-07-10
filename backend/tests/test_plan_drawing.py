"""Dimension chains, label fitting, stair geometry, FloorDrawing (S4.3)."""

import json
import math
import re

from app.engine.geometry import buildable_polygon
from app.engine.plan_geometry import (
    build_floor_drawing,
    derive_dim_chains,
    derive_labels,
    derive_stair,
    derive_walls,
    setback_callouts,
)

from tests.helpers.golden import golden_config, golden_layout
from tests.test_plan_geometry import _room


def _fixture_gf():
    layout = golden_layout()
    return layout.ground_floor, golden_config()


def test_room_chain_sums_to_overall():
    floor, cfg = _fixture_gf()
    walls = derive_walls(floor.rooms, buildable_polygon(cfg))
    chains = derive_dim_chains(floor.rooms, walls, cfg)
    bottom0 = next(c for c in chains if c.side == "bottom" and c.level == 0)
    total = sum(e.end - e.start for e in bottom0.entries)
    assert math.isclose(total, 7.0, abs_tol=1e-3)  # buildable width 8.0 - 1.0
    # entries are contiguous
    for a, b in zip(bottom0.entries, bottom0.entries[1:]):
        assert math.isclose(a.end, b.start, abs_tol=1e-9)


def test_room_chain_includes_internal_walls():
    floor, cfg = _fixture_gf()
    walls = derive_walls(floor.rooms, buildable_polygon(cfg))
    chains = derive_dim_chains(floor.rooms, walls, cfg)
    bottom0 = next(c for c in chains if c.side == "bottom" and c.level == 0)
    bounds = {round(e.start, 3) for e in bottom0.entries} | {
        round(e.end, 3) for e in bottom0.entries
    }
    internal_xs = {
        round(w.x1, 3)
        for w in walls
        if w.kind == "internal" and abs(w.x1 - w.x2) < 1e-9
    }
    # near-parallel walls (<0.3 m apart) are collapsed into one boundary,
    # so each wall must be within 0.3 m of a chain boundary
    for x in internal_xs:
        assert any(abs(x - b) <= 0.3 for b in bounds), x


def test_setback_chains_on_all_sides():
    floor, cfg = _fixture_gf()
    walls = derive_walls(floor.rooms, buildable_polygon(cfg))
    chains = derive_dim_chains(floor.rooms, walls, cfg)
    lvl2 = {c.side for c in chains if c.level == 2}
    assert lvl2 == {"bottom", "top", "left", "right"}
    left2 = next(c for c in chains if c.side == "left" and c.level == 2)
    assert len(left2.entries) == 3  # front setback / building / rear setback
    assert math.isclose(
        sum(e.end - e.start for e in left2.entries), cfg.plot_length, abs_tol=1e-6
    )


def test_dim_lanes_do_not_collide():
    floor, cfg = _fixture_gf()
    walls = derive_walls(floor.rooms, buildable_polygon(cfg))
    chains = derive_dim_chains(floor.rooms, walls, cfg)
    for side in ("bottom", "top", "left", "right"):
        coords = [c.coord for c in chains if c.side == side]
        assert len(coords) == len(set(round(c, 6) for c in coords))


def test_dim_text_formats_by_level():
    """L0 room chains: ft-in. L1 overall: dual-unit. L2: metric setbacks,
    ft-in building span (municipal convention — setbacks are quoted in metres)."""
    floor, cfg = _fixture_gf()
    walls = derive_walls(floor.rooms, buildable_polygon(cfg))
    chains = derive_dim_chains(floor.rooms, walls, cfg)
    for c in chains:
        for i, e in enumerate(c.entries):
            if c.level == 0:
                assert re.match(r"^\d+'-\d+\"$", e.text), e.text
            elif c.level == 1:
                assert re.match(r"^\d+'-\d+\" \(\d+\.\d+ m\)$", e.text), e.text
            elif i in (0, len(c.entries) - 1):
                assert re.match(r"^\d+\.\d+M$", e.text), e.text
            else:
                assert re.match(r"^\d+'-\d+\"$", e.text), e.text


def test_overall_chain_spans_full_plot_dual_unit():
    floor, cfg = _fixture_gf()
    walls = derive_walls(floor.rooms, buildable_polygon(cfg))
    chains = derive_dim_chains(floor.rooms, walls, cfg)
    lvl1 = [c for c in chains if c.level == 1]
    assert {c.side for c in lvl1} == {"top", "right"}
    top = next(c for c in lvl1 if c.side == "top")
    assert len(top.entries) == 1
    assert math.isclose(
        top.entries[0].end - top.entries[0].start, cfg.plot_width, abs_tol=1e-6
    )


def test_setback_callouts_all_sides():
    cfg = golden_config()
    bounds = buildable_polygon(cfg).bounds
    callouts = setback_callouts(cfg, bounds)
    joined = " ".join(t for t, _x, _y, _rot in callouts)
    assert "FRONT SETBACK" in joined
    assert "REAR SETBACK" in joined
    for text, _x, _y, rotated in callouts:
        if "LEFT" in text or "RIGHT" in text:
            assert rotated is True
        else:
            assert rotated is False


def test_label_fits_inside_normal_room():
    labels = derive_labels([_room("bed", 2.0, 2.0, 3.5, 4.0)])
    lb = labels[0]
    assert lb.leader is None
    assert len(lb.lines) == 4
    assert lb.lines[0] == "BED"
    assert re.match(r"^\(\d+\.\d+ m × \d+\.\d+ m\)$", lb.lines[2]), lb.lines[2]
    assert 6.0 <= lb.font_pt <= 12.0


def test_slim_vertical_room_label_rotates_inside():
    labels = derive_labels(
        [_room("very long utility name", 2.0, 2.0, 0.5, 6.0, rtype="utility")]
    )
    lb = labels[0]
    assert lb.rotated is True and lb.leader is None
    assert lb.lines[0] == "VERY LONG UTILITY NAME"  # never truncated


def test_tiny_room_label_goes_outside_with_leader_untruncated():
    labels = derive_labels(
        [_room("very long utility name", 2.0, 2.0, 0.5, 1.0, rtype="utility")],
        bounds=(1.0, 1.5, 8.0, 14.0),
    )
    lb = labels[0]
    assert lb.leader is not None
    assert lb.cy > 14.0  # stacked above the building, clear of dim lanes
    assert lb.lines[0] == "VERY LONG UTILITY NAME"  # never truncated
    assert "…" not in "".join(lb.lines)


def test_stair_geometry_inside_room():
    floor, _cfg = _fixture_gf()
    stair_room = next(r for r in floor.rooms if r.type == "staircase")
    stair = derive_stair(floor.rooms)
    assert stair is not None
    assert 8 <= stair.tread_count <= 13
    for x1, y1, x2, y2 in stair.treads:
        assert stair_room.x - 1e-6 <= min(x1, x2)
        assert max(x1, x2) <= stair_room.x + stair_room.width + 1e-6
        assert stair_room.y - 1e-6 <= min(y1, y2)
        assert max(y1, y2) <= stair_room.y + stair_room.depth + 1e-6
    assert stair.break_line is not None


def test_build_floor_drawing_serializes_stably():
    layout = golden_layout()
    cfg = golden_config()
    for floor in (layout.ground_floor, layout.first_floor):
        d1 = build_floor_drawing(floor, cfg).to_dict()
        d2 = build_floor_drawing(floor, cfg).to_dict()
        s1 = json.dumps(d1, sort_keys=True)
        assert s1 == json.dumps(d2, sort_keys=True)
        assert d1["version"] == 1
        for key in ("walls", "openings", "columns", "dim_chains", "labels", "bounds"):
            assert key in d1, key
        assert d1["walls"] and d1["openings"] and d1["columns"]


def test_to_dict_floats_rounded():
    layout = golden_layout()
    cfg = golden_config()
    d = build_floor_drawing(layout.ground_floor, cfg).to_dict()

    def check(node):
        if isinstance(node, float):
            assert node == round(node, 4)
        elif isinstance(node, list):
            for v in node:
                check(v)
        elif isinstance(node, dict):
            for v in node.values():
                check(v)

    check(d)
