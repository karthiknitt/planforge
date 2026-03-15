"""Unit tests for cad_primitives.py"""
import pytest

from app.engine.cad_primitives import Opening, _gap_subtract, collect_openings, metres_to_ftin
from app.engine.models import Room


# ---------------------------------------------------------------------------
# metres_to_ftin
# ---------------------------------------------------------------------------

def test_metres_to_ftin_whole_feet():
    assert metres_to_ftin(3.048) == "10'-0\""


def test_metres_to_ftin_with_inches():
    assert metres_to_ftin(1.067) == "3'-6\""


def test_metres_to_ftin_zero():
    assert metres_to_ftin(0.0) == "0'-0\""


def test_metres_to_ftin_inch_rollover():
    # 0.3048 = 1 foot exactly; check boundary
    result = metres_to_ftin(0.3048)
    assert result == "1'-0\""


# ---------------------------------------------------------------------------
# _gap_subtract
# ---------------------------------------------------------------------------

def test_gap_subtract_no_gaps():
    segs = _gap_subtract(5.0, [])
    assert segs == [(0.0, 5.0)]


def test_gap_subtract_single_gap_middle():
    segs = _gap_subtract(5.0, [(2.0, 3.0)])
    assert segs == [(0.0, 2.0), (3.0, 5.0)]


def test_gap_subtract_gap_at_start():
    segs = _gap_subtract(5.0, [(0.0, 1.0)])
    assert segs == [(1.0, 5.0)]


def test_gap_subtract_gap_at_end():
    segs = _gap_subtract(5.0, [(4.0, 5.0)])
    assert segs == [(0.0, 4.0)]


def test_gap_subtract_full_gap():
    segs = _gap_subtract(5.0, [(0.0, 5.0)])
    assert segs == []


def test_gap_subtract_multiple_gaps():
    segs = _gap_subtract(10.0, [(1.0, 2.0), (5.0, 6.0), (8.0, 9.0)])
    assert segs == [(0.0, 1.0), (2.0, 5.0), (6.0, 8.0), (9.0, 10.0)]


def test_gap_subtract_unsorted_gaps():
    # gaps provided out of order — should still work
    segs = _gap_subtract(10.0, [(5.0, 6.0), (1.0, 2.0)])
    assert segs == [(0.0, 1.0), (2.0, 5.0), (6.0, 10.0)]


# ---------------------------------------------------------------------------
# collect_openings — helper fixtures
# ---------------------------------------------------------------------------

def _make_room(rid, name, rtype, x, y, width, depth):
    return Room(id=rid, name=name, type=rtype, x=x, y=y, width=width, depth=depth)


def _two_adjacent_rooms_vertical():
    """Two rooms side-by-side: living (0–3, 0–4) | bedroom (3–6, 0–4)."""
    ra = _make_room("r1", "Living", "living", 0.0, 0.0, 3.0, 4.0)
    rb = _make_room("r2", "Bedroom", "bedroom", 3.0, 0.0, 3.0, 4.0)
    return [ra, rb], 0.0, 0.0, 6.0, 4.0


def _room_touching_front():
    """One habitable room touching front (y=0)."""
    r = _make_room("r1", "Living", "living", 0.0, 0.0, 6.0, 4.0)
    return [r], 0.0, 0.0, 6.0, 4.0


def _toilet_touching_exterior():
    """Toilet at front wall."""
    r = _make_room("r1", "Toilet", "toilet", 0.0, 0.0, 2.0, 2.0)
    return [r], 0.0, 0.0, 2.0, 2.0


# ---------------------------------------------------------------------------
# collect_openings — door detection
# ---------------------------------------------------------------------------

def test_collect_openings_finds_door_on_shared_vertical_wall():
    rooms, bld_x, bld_y, bld_w, bld_d = _two_adjacent_rooms_vertical()
    result = collect_openings(rooms, 0.23, 0.115, bld_x, bld_y, bld_w, bld_d)

    # There should be at least one wall with a door opening
    door_openings = [op for ops in result.values() for op in ops if op.kind == "door"]
    assert len(door_openings) >= 1


def test_collect_openings_door_on_correct_wall():
    rooms, bld_x, bld_y, bld_w, bld_d = _two_adjacent_rooms_vertical()
    result = collect_openings(rooms, 0.23, 0.115, bld_x, bld_y, bld_w, bld_d)

    # Shared wall is at x=3.0 — key should be (3.0, 0.0, 3.0, 4.0)
    expected_key = (3.0, 0.0, 3.0, 4.0)
    assert expected_key in result
    door_ops = [op for op in result[expected_key] if op.kind == "door"]
    assert len(door_ops) == 1


# ---------------------------------------------------------------------------
# collect_openings — window detection
# ---------------------------------------------------------------------------

def test_collect_openings_finds_window_on_exterior():
    rooms, bld_x, bld_y, bld_w, bld_d = _room_touching_front()
    result = collect_openings(rooms, 0.23, 0.115, bld_x, bld_y, bld_w, bld_d)

    win_ops = [op for ops in result.values() for op in ops if op.kind == "window"]
    assert len(win_ops) >= 1


# ---------------------------------------------------------------------------
# collect_openings — ventilator detection
# ---------------------------------------------------------------------------

def test_collect_openings_ventilator_for_toilet():
    rooms, bld_x, bld_y, bld_w, bld_d = _toilet_touching_exterior()
    result = collect_openings(rooms, 0.23, 0.115, bld_x, bld_y, bld_w, bld_d)

    vent_ops = [op for ops in result.values() for op in ops if op.kind == "ventilator"]
    assert len(vent_ops) >= 1


# ---------------------------------------------------------------------------
# Opening gaps are sorted and non-overlapping
# ---------------------------------------------------------------------------

def test_opening_gaps_are_sorted():
    rooms, bld_x, bld_y, bld_w, bld_d = _two_adjacent_rooms_vertical()
    result = collect_openings(rooms, 0.23, 0.115, bld_x, bld_y, bld_w, bld_d)

    for ops in result.values():
        for i in range(len(ops) - 1):
            assert ops[i].t_start <= ops[i + 1].t_start, "Openings not sorted by t_start"


def test_opening_t_values_in_range():
    rooms, bld_x, bld_y, bld_w, bld_d = _two_adjacent_rooms_vertical()
    result = collect_openings(rooms, 0.23, 0.115, bld_x, bld_y, bld_w, bld_d)

    for ops in result.values():
        for op in ops:
            assert 0.0 <= op.t_start <= 1.0, f"t_start={op.t_start} out of range"
            assert 0.0 <= op.t_end <= 1.0, f"t_end={op.t_end} out of range"
            assert op.t_start < op.t_end, "t_start must be less than t_end"


# ---------------------------------------------------------------------------
# Wall key round-trip
# ---------------------------------------------------------------------------

def test_wall_key_format_matches_openings_map():
    """Wall keys from collect_openings must match (round(x1,2),...) format."""
    rooms, bld_x, bld_y, bld_w, bld_d = _two_adjacent_rooms_vertical()
    result = collect_openings(rooms, 0.23, 0.115, bld_x, bld_y, bld_w, bld_d)

    for key in result:
        assert len(key) == 4, "Wall key should be 4-tuple"
        x1, y1, x2, y2 = key
        # Values should be rounded to 2dp (as stored)
        assert x1 == round(x1, 2)
        assert y1 == round(y1, 2)
