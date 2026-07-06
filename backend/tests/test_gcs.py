"""Geometric Correctness Score (Sprint 7) — the deterministic export quality
gate computed from the canonical FloorDrawing, replacing CCQS's pixel/text
heuristics. Unlike CCQS these are pass/fail structural invariants (should
always hold once every renderer shares one derivation), not fuzzy scores —
so this asserts the invariants directly rather than comparing to a baseline.
"""

from app.quality.ccqs import GCS_MAX, compute_gcs
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


def test_perfect_score():
    result = _gcs()
    assert result.total == GCS_MAX
    assert result.as_dict()["max"] == GCS_MAX
