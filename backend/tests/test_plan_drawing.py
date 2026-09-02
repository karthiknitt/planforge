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
        sum(e.end - e.start for e in left2.entries), cfg.plot_y_extent, abs_tol=1e-6
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
        top.entries[0].end - top.entries[0].start, cfg.plot_x_extent, abs_tol=1e-6
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


def _label_footprint(lb):
    """Absolute-sheet AABB for a LabelBox, mirroring how derive_labels()
    itself measures a candidate before accepting it."""
    from shapely.geometry import box

    from app.engine.plan_geometry import _PT_TO_MODEL_M, _text_width_m

    w = max(_text_width_m(t, lb.font_pt) for t in lb.lines)
    h = len(lb.lines) * lb.font_pt * 1.3 * _PT_TO_MODEL_M
    if lb.rotated:
        w, h = h, w
    return box(lb.cx - w / 2, lb.cy - h / 2, lb.cx + w / 2, lb.cy + h / 2)


def test_staircase_label_does_not_collide_with_room_above():
    # A staircase's label is centered 2/3 down its depth (not at the true
    # centre), so at these realistic dimensions the fitted label's own
    # height pushes past the room's top edge into whatever sits above it —
    # reproduced directly against derive_labels() before any fix: the
    # staircase's box top (2.092) sits below the room-above's label bottom
    # (2.012), a real 0.08m overlap in absolute sheet coordinates.
    stair = _room("stair", 0.0, 0.0, 2.4, 1.9, rtype="staircase")
    above = _room("above", 0.0, 1.9, 1.0, 0.5, rtype="utility")
    labels = derive_labels([stair, above])
    assert len(labels) == 2
    boxes = {lb.room_id: _label_footprint(lb) for lb in labels}
    assert not boxes["stair"].intersects(boxes["above"]), (
        "staircase label overlaps the room above it: "
        f"{boxes['stair'].bounds} vs {boxes['above'].bounds}"
    )


def test_non_colliding_rooms_keep_full_labels():
    # Control: two ordinary, well-separated rooms should be entirely
    # unaffected by collision avoidance -- both keep their best-fit label.
    a = _room("a", 0.0, 0.0, 3.5, 4.0, rtype="bedroom")
    b = _room("b", 10.0, 10.0, 3.5, 4.0, rtype="bedroom")
    labels = derive_labels([a, b])
    assert len(labels) == 2
    for lb in labels:
        assert lb.leader is None
        assert len(lb.lines) == 4
        assert lb.font_pt == 12.0


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
        assert d1["version"] == 2
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


# ── Payload v2: version bump, v1 rehydration, lossless round-trip (T28) ──────


def test_v2_payload_round_trips_losslessly():
    from app.engine.cad_elements import FloorDrawing

    d = build_floor_drawing(golden_layout().ground_floor, golden_config())
    payload = d.to_dict()
    assert payload["version"] == 2
    rehydrated = FloorDrawing.from_dict(payload)
    assert rehydrated.to_dict() == payload


def test_stored_v1_payload_rehydrates_and_renders():
    """Revision snapshots taken before Phase 7 froze version-1 drawings with
    no wall/opening ids, no opening marks (T27/28), no site context (T32)
    and no fixtures (T33). Such a payload must still deserialise (defaults
    for the new fields) and render."""
    from app.engine.cad_elements import FloorDrawing

    d = build_floor_drawing(golden_layout().ground_floor, golden_config())
    v1 = d.to_dict()
    v1["version"] = 1
    for w in v1["walls"]:
        w.pop("id", None)
    for o in v1["openings"]:
        o.pop("id", None)
        o.pop("mark", None)
    v1.pop("site", None)
    v1.pop("fixtures", None)

    old = FloorDrawing.from_dict(v1)
    assert len(old.walls) == len(v1["walls"])
    assert len(old.openings) == len(v1["openings"])
    assert all(w.id == "" for w in old.walls)
    assert all(o.id == "" and o.mark == "" for o in old.openings)
    assert old.site is None
    assert old.fixtures == []
    # renders: a rehydrated drawing serialises again as a current v2 payload
    again = old.to_dict()
    assert again["version"] == 2
    assert len(again["walls"]) == len(v1["walls"])
    # unknown future keys are ignored rather than rejected
    v1["something_new"] = {"nested": True}
    assert FloorDrawing.from_dict(v1).to_dict()["version"] == 2


def test_unknown_dim_chain_keys_are_ignored_not_rejected():
    """CodeRabbit finding on PR #97: dim_chains construction indexed straight
    into the payload dict (`d["side"]`, `DimChainEntry(**e)`) instead of going
    through `_take()` like every sibling list here, so a future/unknown key on
    a dim-chain or its entries raised TypeError instead of degrading
    gracefully — breaking from_dict's own documented "unknown keys are
    ignored" contract."""
    from app.engine.cad_elements import FloorDrawing

    d = build_floor_drawing(golden_layout().ground_floor, golden_config())
    payload = d.to_dict()
    assert payload["dim_chains"], "fixture must have at least one dim chain"
    payload["dim_chains"][0]["future_chain_field"] = "ignore me"
    if payload["dim_chains"][0]["entries"]:
        payload["dim_chains"][0]["entries"][0]["future_entry_field"] = "ignore me too"
    rehydrated = FloorDrawing.from_dict(payload)
    assert len(rehydrated.dim_chains) == len(payload["dim_chains"])


def _dim_text_width_m(text: str, font_pt: float = 6.0) -> float:
    """Width of a dimension string in MODEL metres, as _draw_dim_chains draws it.

    _draw_dim_chains centres every entry's text at 6 pt Helvetica (level 1 uses
    6.5 pt bold), so this is the space each string actually occupies on the
    sheet, converted back into plan metres at 1:100.
    """
    from reportlab.pdfbase import pdfmetrics

    from app.engine.plan_geometry import _PT_TO_MODEL_M

    return pdfmetrics.stringWidth(text, "Helvetica", font_pt) * _PT_TO_MODEL_M


def test_dim_chain_entries_are_wide_enough_for_their_own_text():
    """A dim segment must be at least as wide as the text that labels it.

    `derive_dim_chains` merged coordinate lines closer than a flat 0.30 m --
    a purely geometric floor with no reference to text metrics. The narrowest
    string the renderer can emit ("1'-2\"") is 0.421 m wide at 6 pt, so every
    segment in the 0.30-0.42 m band was guaranteed to carry text wider than
    itself, and `_draw_dim_chains` centres each string unconditionally. The
    result is the vision judge's "stack of overlapping strings printed on top
    of each other".
    """
    floor, cfg = _fixture_gf()
    # Slivers just above the old 0.30 m floor: these survive the merge but
    # cannot fit their own label.
    rooms = list(floor.rooms)
    x0 = cfg.setback_left + 0.115
    for i in range(3):
        rooms.append(
            _room(f"sliver{i}", x0 + i * 0.32, cfg.setback_front + 0.115, 0.32, 0.9)
        )
    walls = derive_walls(rooms, buildable_polygon(cfg))
    chains = derive_dim_chains(rooms, walls, cfg)

    offenders = []
    for ch in chains:
        for e in ch.entries:
            span = e.end - e.start
            need = _dim_text_width_m(e.text, 6.5 if ch.level == 1 else 6.0)
            if need > span + 1e-9:
                offenders.append(
                    (ch.side, ch.level, e.text, round(span, 3), round(need, 3))
                )
    assert not offenders, (
        f"{len(offenders)} dim entries carry text wider than their own segment "
        f"(side, level, text, span_m, needed_m): {offenders[:6]}"
    )


def test_labels_avoid_the_section_cut_line():
    """No room label may sit on the A-A section cut line.

    The cut line is drawn straight across the plan by `_draw_section_marker`,
    but `derive_labels()` never knew it existed, so captions in its path were
    struck through. The vision judge reported this on both judged designs:
    "the A-A section cut line and its centreline run straight through the
    DINING AREA and CAR PORCH labels" and "the section line A-A and its cut
    markers run straight through the CAR PORCH / STAIRCASE / DINING label
    stack, further obscuring the already-crowded left column".
    """
    from app.engine.plan_geometry import _label_footprint
    from app.engine.section_geometry import section_cut_line

    floor, cfg = _fixture_gf()
    buildable = buildable_polygon(cfg)
    drawing = build_floor_drawing(floor, cfg)
    line, _ = section_cut_line(floor.rooms, buildable)

    struck = []
    for lb in drawing.labels:
        fp = _label_footprint(lb.cx, lb.cy, lb.lines, lb.font_pt, lb.rotated)
        if fp.intersects(line):
            struck.append((lb.lines[0], round(lb.cx, 2), round(lb.cy, 2)))
    assert not struck, (
        f"{len(struck)} labels struck through by section line A-A: {struck}"
    )
