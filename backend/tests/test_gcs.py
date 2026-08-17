"""Geometric Correctness Score (Sprint 7) — the deterministic export quality
gate computed from the canonical FloorDrawing, replacing CCQS's pixel/text
heuristics. Unlike CCQS these are pass/fail structural invariants (should
always hold once every renderer shares one derivation), not fuzzy scores —
so this asserts the invariants directly rather than comparing to a baseline.
"""

from app.engine.cad_elements import Opening, WallJunction, WallSegment
from app.quality.ccqs import GCS_MAX, _opening_clearance_violations, compute_gcs
from tests.helpers.golden import golden_config, golden_layout


def _gcs():
    layout = golden_layout()
    cfg = golden_config()
    return compute_gcs(layout.ground_floor, cfg)


def test_no_phantom_walls():
    assert _gcs().phantom_walls == 0


def test_no_opening_collisions():
    assert _gcs().collisions == 0


def test_no_label_overflow():
    assert _gcs().label_overflow == 0


def test_full_dimension_coverage():
    assert _gcs().dimension_coverage_pct == 100.0


def test_standard_scale():
    assert _gcs().standard_scale is True


def test_every_room_has_a_door():
    assert _gcs().doors_per_room_ok is True


def test_every_habitable_room_has_a_window():
    assert _gcs().windows_per_habitable_ok is True


def test_golden_layout_has_the_known_zero_pier_defect():
    """The golden layout butts its main entrance door straight against the
    adjacent living-room window: pier = 0.000 m, no masonry between them.

    That is a real placement defect, found by this metric when it was added
    (Task 9E), NOT a metric artefact — `plan_geometry._ObstacleIndex`
    registers an already-placed opening with a half-extent of exactly
    `width / 2`, so unlike columns (which get `_COL_CLEAR`) openings are
    allowed to abut with zero clearance. `_JAMB` is enforced against wall
    ENDS only, never between two openings.

    Fixing that is a placement-code change (it moves every layout's
    geometry) and is deliberately out of scope here. This test pins the
    current honest behaviour and will fail loudly — as it should — the day
    the placement gap is closed.
    """
    result = _gcs()
    assert result.opening_clearance_violations == 2
    reasons = result.debug["opening_clearance"]
    assert len(reasons) == 2
    assert all("pier" in r for r in reasons), reasons


def test_score_is_max_minus_only_the_pier_deduction():
    """Every other GCS dimension is still clean on the golden layout, so the
    total must be exactly the 10-point opening-clearance deduction below the
    max. Written as an identity rather than a bare number so a change to any
    OTHER sub-metric's weight cannot silently pass."""
    result = _gcs()
    assert result.as_dict()["max"] == GCS_MAX
    assert result.phantom_walls == 0
    assert result.collisions == 0
    assert result.label_overflow == 0
    assert result.dimension_coverage_pct == 100.0
    assert result.standard_scale is True
    assert result.doors_per_room_ok is True
    assert result.windows_per_habitable_ok is True
    assert result.total == GCS_MAX - 10


# ── _opening_clearance_violations, exercised directly ─────────────────────
# One 10 m horizontal wall at y=0, with a T-junction at x=5.0 where an
# internal wall lands on it. Openings are placed onto it per case.

_WALL = [WallSegment(0.0, 0.0, 10.0, 0.0, 0.23, "external")]
_JUNCTIONS = [WallJunction(x=5.0, y=0.0, degree=3)]


def _window(cx: float, width: float = 1.2) -> Opening:
    return Opening(
        kind="window",
        cx=cx,
        cy=0.0,
        width=width,
        is_horizontal=True,
        wall_thickness=0.23,
    )


def test_clearance_passes_for_well_placed_openings():
    """The control: without it, every negative case below would also pass
    against a checker that simply flags everything."""
    count, reasons = _opening_clearance_violations(
        [_window(2.0), _window(7.5)], _WALL, _JUNCTIONS
    )
    assert count == 0, reasons


def test_clearance_flags_opening_too_close_to_a_wall_end():
    count, reasons = _opening_clearance_violations(
        [_window(0.65)], _WALL, _JUNCTIONS
    )  # left edge at 0.05 m, under the 0.115 m minimum
    assert count == 1
    assert "jamb clearance" in reasons[0], reasons


def test_clearance_flags_opening_too_close_to_a_perpendicular_wall():
    """Measured to the T-junction at x=5.0, not to the wall run's far end —
    the run itself is 10 m long, so a run-ends-only check would pass this."""
    count, reasons = _opening_clearance_violations(
        [_window(4.35)], _WALL, _JUNCTIONS
    )  # right edge at 4.95 m, only 0.05 m short of the junction
    assert count == 1
    assert "jamb clearance" in reasons[0], reasons


def test_clearance_flags_a_sliver_pier_between_two_openings():
    count, reasons = _opening_clearance_violations(
        [_window(2.0), _window(3.25)], _WALL, _JUNCTIONS
    )  # 0.05 m of masonry between them
    assert count == 2, reasons  # both openings are implicated
    assert len(reasons) == 2
    assert all("pier" in r for r in reasons), reasons


def test_clearance_flags_an_opening_spanning_a_junction():
    count, reasons = _opening_clearance_violations(
        [_window(5.0, width=2.0)], _WALL, _JUNCTIONS
    )
    assert count == 1
    assert "spans a wall junction" in reasons[0], reasons


def test_clearance_reports_an_overhang_as_an_overhang_not_a_junction():
    """An opening whose centre is on the run but whose edge runs off the end
    is a different defect from one straddling a mid-run junction, and must
    not borrow the junction wording — this string is what the baseline test
    prints on failure."""
    count, reasons = _opening_clearance_violations(
        [_window(9.7)], _WALL, _JUNCTIONS
    )  # spans 9.1..10.3 on a run ending at 10.0
    assert count == 1
    assert "extends past its wall run" in reasons[0], reasons
    assert "junction" not in reasons[0], reasons


def test_clearance_flags_an_opening_on_no_wall_at_all():
    count, reasons = _opening_clearance_violations([_window(20.0)], _WALL, _JUNCTIONS)
    assert count == 1
    assert "lies on no wall run" in reasons[0], reasons
