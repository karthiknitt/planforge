"""Room-semantics guards: no absurd wet rooms, type-aware absorption (S5.4)."""

import json
from pathlib import Path

from app.engine.generator import (
    _absorb_into_adjacent,
    _split_oversized_wet_rooms,
)
from app.engine.models import FloorPlan, Room

from tests.helpers.golden import golden_layout

CONFIG_DIR = Path(__file__).parent.parent / "app" / "config"

IWT = 0.115
WET_CAP_SQM = 6.0


def _room(rid, rtype, x, y, w, d):
    return Room(
        id=rid,
        name=rid.replace("_", " ").title(),
        type=rtype,
        x=x,
        y=y,
        width=w,
        depth=d,
    )


def test_split_carves_oversized_toilet_into_toilet_plus_passage():
    # the golden fixture's infamous 5.5m-wide "Toilet 2" band (16.6 sqm)
    fp = FloorPlan(
        floor=1,
        rooms=[
            _room("ff_stair", "staircase", 1.23, 1.73, 0.9, 3.0),
            _room("ff_toilet_2", "toilet", 2.245, 1.73, 5.525, 3.0),
        ],
    )
    notes = _split_oversized_wet_rooms(fp)
    toilet = next(r for r in fp.rooms if r.type == "toilet")
    assert toilet.area <= WET_CAP_SQM + 0.01, f"toilet still {toilet.area} sqm"
    # Remainder is typed by size: room-sized remainders become a real room
    # (Family Lounge, living) instead of a giant mislabelled "Passage".
    remainder = [r for r in fp.rooms if r.id == "ff_toilet_2_passage"]
    assert remainder, "remainder not carved off the oversized toilet"
    assert remainder[0].type == "living", remainder[0].type
    assert remainder[0].name == "Family Lounge"
    # split leaves the standard iwt gap between the two new rooms
    gap = remainder[0].x - (toilet.x + toilet.width)
    if gap < 0:
        gap = toilet.x - (remainder[0].x + remainder[0].width)
    assert abs(gap - IWT) < 1e-6
    assert notes, "split should be reported in space notes"


def test_split_leaves_compliant_toilets_alone():
    fp = FloorPlan(
        floor=0,
        rooms=[
            _room("gf_toilet", "toilet", 1.23, 1.73, 1.5, 2.2),  # 3.3 sqm, fine
        ],
    )
    before = [(r.id, r.x, r.width) for r in fp.rooms]
    _split_oversized_wet_rooms(fp)
    assert [(r.id, r.x, r.width) for r in fp.rooms] == before


def test_absorption_prefers_non_wet_neighbour():
    from shapely.geometry import box

    # leftover band sits above BOTH rooms; toilet is bigger but must not absorb
    toilet = _room("t", "toilet", 1.23, 1.73, 3.0, 2.0)
    bed = _room("b", "bedroom", 4.345, 1.73, 2.0, 2.0)
    fp = FloorPlan(floor=0, rooms=[toilet, bed])
    region = box(1.23, 3.73, 6.345, 5.0)
    _absorb_into_adjacent(fp, region, 1.23, 3.73, 6.345, 5.0, [])
    assert toilet.depth == 2.0, "wet room absorbed the leftover band"
    assert bed.depth > 2.0, "non-wet neighbour should have absorbed"


def test_golden_fixture_after_split_has_no_absurd_wet_rooms():
    layout = golden_layout()
    for fp in (layout.ground_floor, layout.first_floor):
        _split_oversized_wet_rooms(fp)
        for r in fp.rooms:
            if r.type not in {"toilet", "wc_only", "bathroom_master"}:
                continue
            # narrow slivers (<~0.94 m) cannot be split into a min-area
            # toilet — they stay whole; every splittable room must be sane
            if min(r.width, r.depth) >= 0.94:
                assert r.area <= WET_CAP_SQM + 0.01, (r.id, r.area)
                aspect = max(r.width, r.depth) / min(r.width, r.depth)
                assert aspect <= 3.5, (r.id, aspect)
            # split or not, a wet room never falls below the 2.8 sqm minimum
            assert r.area >= 2.8, (r.id, r.area)


def test_split_never_produces_sub_minimum_toilet():
    # 0.75 m band: too narrow to split — must stay whole and compliant
    fp = FloorPlan(
        floor=0,
        rooms=[_room("gf_toilet_1", "toilet", 7.019, 6.059, 0.751, 7.711)],
    )
    _split_oversized_wet_rooms(fp)
    toilet = next(r for r in fp.rooms if r.type == "toilet")
    assert toilet.area >= 2.8
    assert len(fp.rooms) == 1  # no split happened


def test_toilet_sizing_calibrated_to_indian_conventions_and_kept_in_sync():
    """Both room_specs.json and compliance_rules.json must agree on the
    Indian-convention toilet/bathroom caps (5'x7' ~= 3.25 sqm standard bath;
    NBC minimums unchanged)."""
    compliance = json.loads((CONFIG_DIR / "compliance_rules.json").read_text())
    room_specs = json.loads((CONFIG_DIR / "room_specs.json").read_text())

    assert compliance["max_toilet_sqm"] == 4.5
    assert compliance["max_toilet_width_m"] == 2.1
    assert compliance["max_wc_only_sqm"] == 2.0
    assert compliance["min_bathroom_master_sqm"] == 3.2
    assert compliance["max_bathroom_master_sqm"] == 4.5
    assert compliance["min_bathroom_master_width_m"] == 1.5
    # unchanged minimums
    assert compliance["min_toilet_sqm"] == 2.8
    assert compliance["min_wc_only_sqm"] == 1.1

    assert room_specs["toilet"]["max_area_sqm"] == compliance["max_toilet_sqm"]
    assert room_specs["toilet"]["max_width_m"] == compliance["max_toilet_width_m"]
    assert room_specs["wc_only"]["max_area_sqm"] == compliance["max_wc_only_sqm"]
    assert (
        room_specs["bathroom_master"]["min_area_sqm"]
        == compliance["min_bathroom_master_sqm"]
    )
    assert (
        room_specs["bathroom_master"]["max_area_sqm"]
        == compliance["max_bathroom_master_sqm"]
    )
    assert (
        room_specs["bathroom_master"]["min_width_m"]
        == compliance["min_bathroom_master_width_m"]
    )
