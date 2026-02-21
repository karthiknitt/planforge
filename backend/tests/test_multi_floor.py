"""Tests for multi-floor compliance checks (Phase E)."""

import pytest
from app.engine.compliance import check, load_rules
from app.engine.models import Column, ComplianceResult, FloorPlan, Layout, PlotConfig, Room


def _room(id, type, x, y, w, d):
    return Room(id=id, name=type.title(), type=type, x=x, y=y, width=w, depth=d)


def _make_layout(gf_rooms, ff_rooms=None, sf_rooms=None, basement_rooms=None,
                 gf_type="ground") -> Layout:
    gf = FloorPlan(floor=0, floor_type=gf_type, rooms=gf_rooms or [])
    ff = FloorPlan(floor=1, floor_type="first", rooms=ff_rooms or [])
    sf = FloorPlan(floor=2, floor_type="second", rooms=sf_rooms) if sf_rooms is not None else None
    bsmt = FloorPlan(floor=-1, floor_type="basement", rooms=basement_rooms, needs_mech_ventilation=True) if basement_rooms is not None else None
    return Layout(id="T", name="Test", ground_floor=gf, first_floor=ff,
                  second_floor=sf, basement_floor=bsmt,
                  compliance=ComplianceResult(passed=True))


def _cfg(**kw):
    d = dict(
        plot_length=14.0, plot_width=11.0,
        setback_front=1.5, setback_rear=1.0,
        setback_left=0.9, setback_right=0.9,
        num_bedrooms=3, toilets=3, parking=False, city="other",
    )
    d.update(kw)
    return PlotConfig(**d)


def test_stilt_with_bedroom_fails():
    bedroom = _room("b", "bedroom", 1.13, 1.73, 3.0, 3.5)
    layout = _make_layout([bedroom], gf_type="stilt")
    cfg = _cfg()
    rules = load_rules()
    result = check(layout, cfg, rules)
    assert not result.passed
    assert any("Stilt floor violation" in v for v in result.violations)


def test_stilt_with_parking_passes():
    parking = _room("p", "parking", 1.13, 1.73, 5.0, 5.0)
    layout = _make_layout([parking], gf_type="stilt",
                          ff_rooms=[_room("l", "living", 1.13, 1.73, 4.0, 4.0)])
    cfg = _cfg()
    rules = load_rules()
    result = check(layout, cfg, rules)
    # Should not have stilt violation
    assert not any("Stilt floor violation" in v for v in result.violations)


def test_basement_with_bedroom_fails():
    bedroom = _room("b", "bedroom", 1.13, 1.73, 3.0, 3.5)
    layout = _make_layout(
        gf_rooms=[_room("l", "living", 1.13, 1.73, 4.0, 4.0)],
        basement_rooms=[bedroom],
    )
    cfg = _cfg()
    rules = load_rules()
    result = check(layout, cfg, rules)
    assert not result.passed
    assert any("Basement violation" in v for v in result.violations)


def test_basement_with_gym_passes():
    gym = _room("g", "gym", 1.13, 1.73, 4.0, 4.0)
    layout = _make_layout(
        gf_rooms=[_room("l", "living", 1.13, 1.73, 4.0, 4.0)],
        basement_rooms=[gym],
    )
    cfg = _cfg()
    rules = load_rules()
    result = check(layout, cfg, rules)
    assert not any("Basement violation" in v for v in result.violations)


def test_g_plus_2_adds_structural_warning():
    sf_rooms = [_room("b3", "bedroom", 1.13, 1.73, 3.0, 3.5)]
    layout = _make_layout(
        gf_rooms=[_room("l", "living", 1.13, 1.73, 4.0, 4.0)],
        ff_rooms=[_room("b1", "bedroom", 1.13, 1.73, 3.0, 3.5)],
        sf_rooms=sf_rooms,
    )
    cfg = _cfg()
    rules = load_rules()
    result = check(layout, cfg, rules)
    assert any("structural engineer" in w.lower() for w in result.warnings)
