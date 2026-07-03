"""Regression tests for B3/B4/B5/B6 engine-math fixes.

B3: FAR counts only habitable floors (stilt/basement excluded, G-only = 1 floor).
B4: coverage/FAR use ACTUAL room areas, not the buildable envelope.
B5: trapezoid plots are solved inside the true trapezoid, not the bounding rect.
B6: the solver objective actually optimizes adjacency (was a constant).
"""

from shapely.geometry import box as shp_box

from app.engine.compliance import check, load_rules
from app.engine.generator import generate
from app.engine.geometry import plot_polygon
from app.engine.models import ComplianceResult, FloorPlan, Layout, PlotConfig, Room

RULES = load_rules()


def _room(rid: str, rtype: str, x, y, w, d, name=None) -> Room:
    return Room(id=rid, name=name or rid, type=rtype, x=x, y=y, width=w, depth=d)


class TestFarFloorSemantics:
    def test_stilt_floor_excluded_from_far(self):
        """Plot 50 sqm, default FAR 1.5 → threshold 75 sqm built-up.
        Stilt parking (40) + FF rooms (40) = 40 habitable, under the limit.
        The old code counted the stilt floor too (80 > 75 → false warning)."""
        cfg = PlotConfig(
            plot_length=10.0,
            plot_width=5.0,
            setback_front=0.5,
            setback_rear=0.5,
            setback_left=0.5,
            setback_right=0.5,
            num_bedrooms=1,
            toilets=1,
            parking=True,
            has_stilt=True,
        )
        stilt = FloorPlan(
            floor=0,
            floor_type="stilt",
            rooms=[_room("p1", "parking_4w", 1, 1, 4, 10, "Parking")],
        )
        ff = FloorPlan(
            floor=1,
            floor_type="first",
            rooms=[_room("b1", "bedroom", 1, 1, 4, 10, "Bedroom 1")],
        )
        layout = Layout(
            id="t",
            name="t",
            ground_floor=stilt,
            first_floor=ff,
            compliance=ComplianceResult(passed=True),
        )
        result = check(layout, cfg, RULES)
        assert not any(w.startswith("FAR ") for w in result.warnings), result.warnings


class TestCoverageFromRooms:
    def _cfg(self):
        return PlotConfig(
            plot_length=10.0,
            plot_width=10.0,
            setback_front=1.0,
            setback_rear=1.0,
            setback_left=1.0,
            setback_right=1.0,
            num_bedrooms=1,
            toilets=1,
            parking=False,
        )

    def _layout(self, gf_rooms):
        return Layout(
            id="t",
            name="t",
            ground_floor=FloorPlan(floor=0, floor_type="ground", rooms=gf_rooms),
            first_floor=FloorPlan(floor=1, floor_type="first", rooms=[]),
            compliance=ComplianceResult(passed=True),
        )

    def test_small_footprint_passes_coverage(self):
        """30 sqm of rooms on a 100 sqm plot = 30% coverage. The old code
        reported the ENVELOPE (64%) regardless of what was actually built."""
        rooms = [_room("l1", "living", 1.5, 1.5, 5, 6, "Living")]
        result = check(self._layout(rooms), self._cfg(), RULES)
        assert not any("Floor coverage" in v for v in result.violations)

    def test_oversized_footprint_flagged(self):
        # Small setbacks so the rooms stay INSIDE the boundary (no masking
        # boundary violations) while covering ~71% > the coverage maximum
        cfg = self._cfg()
        cfg.setback_front = cfg.setback_rear = 0.5
        cfg.setback_left = cfg.setback_right = 0.5
        rooms = [
            _room("l1", "living", 0.75, 0.75, 8.5, 4.2, "Living"),
            _room("l2", "dining", 0.75, 5.05, 8.5, 4.2, "Dining"),
        ]
        result = check(self._layout(rooms), cfg, RULES)
        assert any("Floor coverage" in v for v in result.violations), result.violations


class TestTrapezoidSolvedInsideShape:
    def test_generated_rooms_stay_inside_trapezoid(self):
        cfg = PlotConfig(
            plot_length=18.0,
            plot_width=14.0,
            setback_front=1.5,
            setback_rear=1.0,
            setback_left=1.0,
            setback_right=1.0,
            num_bedrooms=2,
            toilets=2,
            parking=False,
            plot_shape="trapezoid",
            plot_front_width=14.0,
            plot_rear_width=9.0,
        )
        layouts = generate(cfg)
        assert layouts, "trapezoid config must produce layouts"
        plot = plot_polygon(cfg).buffer(0.02)  # 2 cm numeric tolerance
        for lay in layouts:
            for fp in (lay.ground_floor, lay.first_floor):
                for r in fp.rooms:
                    room_poly = shp_box(r.x, r.y, r.x + r.width, r.y + r.depth)
                    assert plot.contains(room_poly), (
                        f"{lay.id}/{r.name} pokes outside the trapezoid: "
                        f"{room_poly.bounds}"
                    )


class TestSolverObjectiveIsAlive:
    def test_kitchen_and_dining_are_pulled_together(self):
        """With the distance-minimizing objective, kitchen and dining centres
        must end up close in every solver layout. The old objective maximized
        a constant, so their placement was arbitrary."""
        from app.engine.solver import solve_layouts

        cfg = PlotConfig(
            plot_length=15.0,
            plot_width=10.0,
            setback_front=1.5,
            setback_rear=1.0,
            setback_left=1.0,
            setback_right=1.0,
            num_bedrooms=2,
            toilets=2,
            parking=False,
        )
        layouts = solve_layouts(cfg, ewt=RULES["external_wall_thickness_mm"] / 1000)
        assert layouts, "solver must produce layouts for the standard config"
        for lay in layouts:
            gf = lay.ground_floor.rooms
            kitchen = next((r for r in gf if r.type == "kitchen"), None)
            dining = next((r for r in gf if r.type == "dining"), None)
            if kitchen is None or dining is None:
                continue
            dist = abs(
                (kitchen.x + kitchen.width / 2) - (dining.x + dining.width / 2)
            ) + abs((kitchen.y + kitchen.depth / 2) - (dining.y + dining.depth / 2))
            # Centres within 6 m Manhattan distance on a 10x15 plot — loose
            # enough to be robust, tight enough that a random packing fails
            assert dist < 6.0, f"{lay.id}: kitchen-dining distance {dist:.2f} m"
