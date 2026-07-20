"""Tests for toilet-placement compliance warnings and the attached-bath
check extension (all bedrooms when PlotConfig.attached_toilets is on).
"""

from app.engine.compliance import check, load_rules
from app.engine.models import ComplianceResult, FloorPlan, Layout, PlotConfig, Room

RULES = load_rules()

CFG = PlotConfig(
    plot_length=12.0,
    plot_width=9.0,
    setback_front=1.5,
    setback_rear=1.0,
    setback_left=0.9,
    setback_right=0.9,
    num_bedrooms=2,
    toilets=2,
    parking=False,
)


def _layout(gf_rooms: list[Room]) -> Layout:
    return Layout(
        id="test",
        name="Test",
        ground_floor=FloorPlan(floor=0, floor_type="ground", rooms=gf_rooms),
        first_floor=FloorPlan(floor=1, floor_type="first", rooms=[]),
        compliance=ComplianceResult(passed=True),
    )


def _room(id_: str, type_: str, x: float, y: float, w: float, d: float) -> Room:
    return Room(id=id_, name=type_.title(), type=type_, x=x, y=y, width=w, depth=d)


class TestToiletFrontFacadeWarning:
    def test_front_toilet_warns(self):
        toilet = _room("t1", "toilet", 1.13, 1.73, 1.5, 2.0)
        result = check(_layout([toilet]), CFG, RULES)
        assert any("front facade" in w for w in result.warnings), result.warnings

    def test_back_toilet_no_front_warning(self):
        toilet = _room("t1", "toilet", 1.13, 8.0, 1.5, 2.0)
        result = check(_layout([toilet]), CFG, RULES)
        assert not any("front facade" in w for w in result.warnings)


class TestToiletStairParkingAdjacencyWarning:
    def test_toilet_adjacent_to_staircase_warns(self):
        stair = _room("s", "staircase", 4.87, 5.0, 1.5, 1.5)
        toilet = _room("t", "toilet", 6.37, 5.0, 1.5, 2.0)
        result = check(_layout([stair, toilet]), CFG, RULES)
        assert any("adjacent to staircase" in w for w in result.warnings), (
            result.warnings
        )

    def test_toilet_far_from_staircase_no_warning(self):
        stair = _room("s", "staircase", 4.87, 5.0, 1.5, 1.5)
        toilet = _room("t", "toilet", 1.13, 5.0, 1.5, 2.0)
        result = check(_layout([stair, toilet]), CFG, RULES)
        assert not any("adjacent to staircase" in w for w in result.warnings)

    def test_ensuite_bathroom_exempt_from_stair_penalty(self):
        stair = _room("s", "staircase", 4.87, 5.0, 1.5, 1.5)
        bath = _room("b", "bathroom_master", 6.37, 5.0, 1.5, 2.0)
        bedroom = _room("mb", "master_bedroom", 6.37, 7.0, 1.5, 3.0)
        result = check(_layout([stair, bath, bedroom]), CFG, RULES)
        assert not any("adjacent to staircase" in w for w in result.warnings), (
            result.warnings
        )


class TestToiletExternalWallWarning:
    def test_interior_toilet_warns(self):
        toilet = _room("t", "toilet", 3.13, 5.0, 1.5, 2.0)
        result = check(_layout([toilet]), CFG, RULES)
        assert any("external wall" in w for w in result.warnings), result.warnings

    def test_boundary_toilet_no_warning(self):
        toilet = _room("t", "toilet", 1.13, 5.0, 1.5, 2.0)
        result = check(_layout([toilet]), CFG, RULES)
        assert not any("external wall" in w for w in result.warnings)


class TestAttachedBathCoversAllBedroomsWhenEnabled:
    def test_default_only_checks_master_bedroom(self):
        # No master bedroom present, second bedroom lacks an attached bath —
        # default behaviour (attached_toilets off) must NOT warn about it.
        bedroom = _room("b1", "bedroom", 1.13, 1.73, 3.5, 3.0)
        result = check(_layout([bedroom]), CFG, RULES)
        assert not any(
            "no attached toilet/bathroom detected" in w for w in result.warnings
        )

    def test_attached_toilets_on_checks_every_bedroom(self):
        cfg = PlotConfig(
            plot_length=12.0,
            plot_width=9.0,
            setback_front=1.5,
            setback_rear=1.0,
            setback_left=0.9,
            setback_right=0.9,
            num_bedrooms=2,
            toilets=2,
            parking=False,
        )
        cfg.attached_toilets = True
        bedroom = _room("b1", "bedroom", 1.13, 1.73, 3.5, 3.0)
        result = check(_layout([bedroom]), cfg, RULES)
        assert any(
            "no attached toilet/bathroom detected" in w for w in result.warnings
        ), result.warnings

    def test_attached_toilets_on_with_attached_bath_no_warning(self):
        cfg = PlotConfig(
            plot_length=12.0,
            plot_width=9.0,
            setback_front=1.5,
            setback_rear=1.0,
            setback_left=0.9,
            setback_right=0.9,
            num_bedrooms=2,
            toilets=2,
            parking=False,
        )
        cfg.attached_toilets = True
        bedroom = _room("b1", "bedroom", 1.13, 1.73, 3.5, 3.0)
        bath = _room("t1", "toilet", 4.63, 1.73, 1.5, 2.0)  # shares wall with bedroom
        result = check(_layout([bedroom, bath]), cfg, RULES)
        assert not any(
            "no attached toilet/bathroom detected" in w for w in result.warnings
        ), result.warnings

    def test_missing_attached_toilets_attr_defaults_to_off(self):
        # Simulate a parallel-task checkout where PlotConfig doesn't yet
        # carry the field: getattr(cfg, "attached_toilets", False) must
        # not raise and must behave like default-off.
        bedroom = _room("b1", "bedroom", 1.13, 1.73, 3.5, 3.0)
        result = check(_layout([bedroom]), CFG, RULES)
        assert not any(
            "no attached toilet/bathroom detected" in w for w in result.warnings
        )
