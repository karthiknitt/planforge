"""Tests for the Vastu Shastra compliance checker."""

from app.engine.models import (
    ComplianceResult,
    FloorPlan,
    Layout,
    PlotConfig,
    Room,
)
from app.engine.scorer import _score_vastu
from app.engine.vastu import ZONE_GRIDS, _get_zone, check_vastu

PLOT_W = 9.0
PLOT_L = 12.0


def _make_room(id, type, x, y, w, d, name=None):
    return Room(id=id, name=name or type.title(), type=type, x=x, y=y, width=w, depth=d)


def _make_layout(gf_rooms, id="X"):
    gf = FloorPlan(floor=0, floor_type="ground", rooms=gf_rooms)
    ff = FloorPlan(floor=1, floor_type="first", rooms=[])
    return Layout(
        id=id,
        name=f"Layout {id}",
        ground_floor=gf,
        first_floor=ff,
        compliance=ComplianceResult(passed=True),
    )


def _cfg(road_side="S", vastu_enabled=True):
    return PlotConfig(
        plot_length=PLOT_L,
        plot_width=PLOT_W,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=0.9,
        setback_right=0.9,
        num_bedrooms=2,
        toilets=2,
        parking=False,
        vastu_enabled=vastu_enabled,
        road_side=road_side,
    )


# ── Zone grid rotation ───────────────────────────────────────────────────


def test_zone_grid_road_s_front_left_is_sw():
    # y=0 is road (front) for road_side S; x=0 is west edge → front-left = SW
    assert _get_zone(1.0, 1.0, PLOT_W, PLOT_L, "S") == "SW"


def test_zone_grid_road_s_rear_right_is_ne():
    assert _get_zone(8.0, 11.0, PLOT_W, PLOT_L, "S") == "NE"


def test_zone_grid_road_s_centre_is_c():
    assert _get_zone(PLOT_W / 2, PLOT_L / 2, PLOT_W, PLOT_L, "S") == "C"


def test_zone_grid_road_n_front_left_is_ne():
    # road_side N: y=0 is North (front), east/west swap on x
    assert _get_zone(1.0, 1.0, PLOT_W, PLOT_L, "N") == "NE"


def test_zone_grid_road_e_front_left_is_nw():
    assert _get_zone(1.0, 1.0, PLOT_W, PLOT_L, "E") == "NW"


def test_zone_grid_road_w_front_left_is_se():
    assert _get_zone(1.0, 1.0, PLOT_W, PLOT_L, "W") == "SE"


def test_zone_grid_unknown_road_side_falls_back_to_south():
    assert _get_zone(1.0, 1.0, PLOT_W, PLOT_L, "X") == _get_zone(
        1.0, 1.0, PLOT_W, PLOT_L, "S"
    )


def test_all_grids_are_3x3_and_cover_9_zones():
    for grid in ZONE_GRIDS.values():
        assert len(grid) == 3
        assert all(len(row) == 3 for row in grid)
        flat = {zone for row in grid for zone in row}
        assert flat == {"N", "NE", "E", "SE", "S", "SW", "W", "NW", "C"}


# ── check_vastu: disabled short-circuit ─────────────────────────────────


def test_vastu_disabled_returns_no_findings():
    kitchen = _make_room("k", "kitchen", 0.5, 0.5, 2, 2)  # SW corner, prohibited
    layout = _make_layout([kitchen])
    violations, warnings = check_vastu(layout, _cfg(vastu_enabled=False))
    assert violations == []
    assert warnings == []


# ── check_vastu: prohibit / avoid ────────────────────────────────────────


def test_kitchen_in_sw_is_a_prohibited_violation():
    # SW zone prohibits kitchen per VASTU_RULES
    kitchen = _make_room("k", "kitchen", 0.5, 0.5, 2, 2)
    layout = _make_layout([kitchen])
    violations, warnings = check_vastu(layout, _cfg())
    assert any("kitchen" in v.lower() and "prohibited" in v.lower() for v in violations)


def test_bedroom_in_ne_is_an_avoid_warning():
    # NE zone avoids bedroom (not prohibited)
    bedroom = _make_room("b", "bedroom", 7.0, 11.0, 2, 2)
    layout = _make_layout([bedroom])
    violations, warnings = check_vastu(layout, _cfg())
    assert violations == []
    assert any("bedroom" in w.lower() and "inauspicious" in w.lower() for w in warnings)


def test_room_type_with_no_rules_in_zone_produces_nothing():
    # E zone has no avoid/prohibit list — dining is neutral there
    dining = _make_room("d", "dining", 7.0, 1.0, 2, 2)
    layout = _make_layout([dining])
    violations, warnings = check_vastu(layout, _cfg())
    assert violations == []
    assert warnings == []


# ── check_vastu: bespoke kitchen/pooja/master-bedroom checks ────────────


def test_kitchen_outside_se_nw_e_gets_extra_warning():
    # Kitchen placed in N zone (not SE/NW/E) — separate warning beyond
    # any prohibit/avoid check for the N zone itself (N has no kitchen rule).
    kitchen = _make_room("k", "kitchen", 4.0, 11.0, 2, 2)  # N zone
    layout = _make_layout([kitchen])
    _violations, warnings = check_vastu(layout, _cfg())
    assert any("kitchen is in" in w.lower() for w in warnings)


def test_kitchen_in_se_gets_no_extra_placement_warning():
    kitchen = _make_room("k", "kitchen", 7.0, 1.0, 2, 2)  # SE zone (preferred)
    layout = _make_layout([kitchen])
    _violations, warnings = check_vastu(layout, _cfg())
    assert not any("kitchen is in" in w.lower() for w in warnings)


def test_pooja_outside_ne_n_e_gets_extra_warning():
    pooja = _make_room("p", "pooja", 4.0, 0.5, 2, 2)  # S zone
    layout = _make_layout([pooja])
    _violations, warnings = check_vastu(layout, _cfg())
    assert any("pooja room is in" in w.lower() for w in warnings)


def test_pooja_in_ne_gets_no_extra_placement_warning():
    pooja = _make_room("p", "pooja", 7.0, 11.0, 2, 2)  # NE zone
    layout = _make_layout([pooja])
    _violations, warnings = check_vastu(layout, _cfg())
    assert not any("pooja room is in" in w.lower() for w in warnings)


def test_first_bedroom_outside_sw_s_w_gets_master_bedroom_warning():
    bedroom = _make_room("b", "bedroom", 7.0, 11.0, 2, 2)  # NE zone
    layout = _make_layout([bedroom])
    _violations, warnings = check_vastu(layout, _cfg())
    assert any("ideal for master bedroom" in w.lower() for w in warnings)


def test_first_bedroom_in_sw_gets_no_master_bedroom_warning():
    bedroom = _make_room("b", "bedroom", 0.5, 0.5, 2, 2)  # SW zone
    layout = _make_layout([bedroom])
    _violations, warnings = check_vastu(layout, _cfg())
    assert not any("ideal for master bedroom" in w.lower() for w in warnings)


# ── scorer._score_vastu ───────────────────────────────────────────────


def test_score_vastu_neutral_when_disabled():
    kitchen = _make_room("k", "kitchen", 0.5, 0.5, 2, 2)  # would be a violation
    layout = _make_layout([kitchen])
    assert _score_vastu(layout, _cfg(vastu_enabled=False)) == 100.0


def test_score_vastu_perfect_layout_scores_100():
    kitchen = _make_room("k", "kitchen", 7.0, 1.0, 2, 2)  # SE — preferred, no warning
    layout = _make_layout([kitchen])
    assert _score_vastu(layout, _cfg()) == 100.0


def test_score_vastu_grades_a_prohibited_room_to_zero():
    # Was: "deducts 20 per violation and 5 per warning" — an SW kitchen scored
    # 75.0 because the old component subtracted fixed amounts per check_vastu
    # finding. The component is now the graded vastu_layout_score: a kitchen
    # wholly inside an `avoid` zone earns verdict 0.0 for all of its area.
    kitchen = _make_room("k", "kitchen", 0.5, 0.5, 2, 2)
    layout = _make_layout([kitchen])
    assert _score_vastu(layout, _cfg()) == 0.0


def test_score_vastu_is_bounded_at_zero_however_bad_the_layout():
    # Was: 6 toilets x -20 = -120 clamped to 0 by a max(0.0, ...). There is no
    # clamp now — every verdict factor is in [0, 1], so an area-weighted mean
    # of them cannot leave [0, 100] no matter how many rooms are misplaced.
    rooms = [_make_room(f"t{i}", "toilet", 7.5, 11.5, 1, 1) for i in range(6)]
    layout = _make_layout(rooms)
    assert _score_vastu(layout, _cfg()) == 0.0


def test_score_vastu_ranks_acceptable_between_avoided_and_preferred():
    # The behaviour the old penalty arithmetic could not express: a toilet in S
    # is "acceptable" — worse than the preferred E, better than the avoided NE.
    def _score(x, y):
        return _score_vastu(
            _make_layout([_make_room("t", "toilet", x, y, 2, 2)]), _cfg()
        )

    preferred = _score(6.5, 5.0)  # E
    acceptable = _score(3.5, 1.0)  # S
    avoided = _score(6.5, 9.0)  # NE
    assert preferred == 100.0
    assert acceptable == 70.0
    assert avoided == 0.0
