"""Regression tests for compliance-math fixes (Stage 1 Phase 1, Tier B).

B1: staircase clear width must use the narrower dimension (min), not AND.
B2: beam span must consider both axes (max of width/depth), not width only.
"""

from app.engine.compliance import check, load_rules
from app.engine.models import ComplianceResult, FloorPlan, Layout, PlotConfig, Room

RULES = load_rules()

CFG = PlotConfig(
    plot_y_extent=15.0,
    plot_x_extent=10.0,
    setback_front=1.5,
    setback_rear=1.0,
    setback_left=1.0,
    setback_right=1.0,
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


def _stair(width: float, depth: float) -> Room:
    return Room(
        id="stair-1",
        name="Staircase",
        type="staircase",
        x=0.0,
        y=0.0,
        width=width,
        depth=depth,
    )


class TestStaircaseClearWidth:
    def test_narrow_stair_flagged_even_when_long(self):
        """0.8 m x 3.0 m stair has 0.8 m clear width — must violate the 0.9 m NBC minimum."""
        result = check(_layout([_stair(0.8, 3.0)]), CFG, RULES)
        assert any("Staircase clear width" in v for v in result.violations), (
            f"Expected stair-width violation, got: {result.violations}"
        )

    def test_narrow_stair_flagged_on_other_axis(self):
        result = check(_layout([_stair(3.0, 0.8)]), CFG, RULES)
        assert any("Staircase clear width" in v for v in result.violations)

    def test_compliant_stair_not_flagged(self):
        result = check(_layout([_stair(0.95, 3.0)]), CFG, RULES)
        assert not any("Staircase clear width" in v for v in result.violations)


class TestBeamSpan:
    def test_span_on_depth_axis_flagged(self):
        """3.0 m x 6.0 m room has a 6.0 m clear span on the depth axis."""
        room = Room(
            id="bed-1",
            name="Bedroom 1",
            type="bedroom",
            x=0.0,
            y=0.0,
            width=3.0,
            depth=6.0,
        )
        result = check(_layout([room]), CFG, RULES)
        assert any("span 6.0" in w for w in result.warnings), (
            f"Expected beam-span warning for 6.0 m depth, got: {result.warnings}"
        )

    def test_small_room_no_span_warning(self):
        room = Room(
            id="bed-2",
            name="Bedroom 2",
            type="bedroom",
            x=0.0,
            y=0.0,
            width=3.5,
            depth=4.0,
        )
        result = check(_layout([room]), CFG, RULES)
        assert not any("Bedroom 2: span" in w for w in result.warnings)
