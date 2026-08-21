"""Tests for the rotation-general, area-weighted Vastu zone engine.

Two fixture plots are used deliberately:

* ``SQ`` (10x10) — the historical square fixture. On a square plot a rotation
  about the centroid is an isometry of the plot, so a square fixture cannot
  distinguish a rotation performed in metric space from one performed in
  normalized (aspect-corrected) plot space. Square-only assertions here are
  restricted to things that are genuinely aspect-independent.
* ``NS`` (9.0 x 15.0) — a non-square plot in the shape PlanForge actually
  generates. Every rotation claim is asserted on this plot too, because that is
  the only fixture on which the metric-space and normalized-space
  implementations disagree.
"""

import math

import pytest

from app.engine.models import (
    ComplianceResult,
    FloorPlan,
    Layout,
    PlotConfig,
    Room,
)
from app.engine.vastu import (
    ZONE_GRIDS,
    _get_zone,
    check_vastu,
    north_angle_for_road_side,
    zone_distribution,
    zone_for_point,
)

# Square fixture (historical).
SQ_W, SQ_L = 10.0, 10.0
# Non-square fixture — the one that can actually catch a metric-space rotation.
NS_W, NS_L = 9.0, 15.0

ALL_ZONES = {"N", "NE", "E", "SE", "S", "SW", "W", "NW", "C"}


def _cell_centre(
    row: int, col: int, plot_w: float, plot_l: float
) -> tuple[float, float]:
    """Centre of grid cell [row][col], with row 0 = high y, col 0 = low x."""
    x = plot_w * (col + 0.5) / 3.0
    y = plot_l * (2 - row + 0.5) / 3.0
    return x, y


# ── zone_for_point: unrotated baseline ──────────────────────────────────────


def test_centre_point_is_brahmasthan():
    assert zone_for_point(SQ_W / 2, SQ_L / 2, SQ_W, SQ_L, 0.0) == "C"
    assert zone_for_point(NS_W / 2, NS_L / 2, NS_W, NS_L, 0.0) == "C"


def test_corners_at_zero_rotation():
    for plot_w, plot_l in ((SQ_W, SQ_L), (NS_W, NS_L)):
        lo_x, hi_x = 0.1 * plot_w, 0.9 * plot_w
        lo_y, hi_y = 0.1 * plot_l, 0.9 * plot_l
        assert zone_for_point(lo_x, hi_y, plot_w, plot_l, 0.0) == "NW"
        assert zone_for_point(hi_x, hi_y, plot_w, plot_l, 0.0) == "NE"
        assert zone_for_point(lo_x, lo_y, plot_w, plot_l, 0.0) == "SW"
        assert zone_for_point(hi_x, lo_y, plot_w, plot_l, 0.0) == "SE"


def test_band_boundaries_match_the_historical_thirds():
    """A point exactly on a third boundary keeps the pre-rotation bucket.

    The superseded ``_get_zone`` bucketed with ``<`` on both column comparisons
    (``cx < plot_w / 3``, ``cx < 2 * plot_w / 3``) and ``>`` on both row
    comparisons (``cy > 2 * plot_l / 3``, ``cy > plot_l / 3``). That makes the
    tie behaviour **asymmetric**, not "middle band on both axes":

    ======================  ==========  ==============
    boundary                lands in    on 9.0 x 15.0
    ======================  ==========  ==============
    ``x = W/3``   (low-x)   middle      ``C``
    ``x = 2W/3``  (high-x)  outer       ``E``
    ``y = L/3``   (low-y)   outer       ``S``
    ``y = 2L/3``  (high-y)  middle      ``C``
    ======================  ==========  ==============

    All four are pinned below (measured against the ``405cdb9`` code, not
    assumed) — an earlier revision of this test covered only the two
    middle-band ties, and mutating either of the two outer-band comparisons
    alone survived the whole file.

    Rewriting the buckets in normalized space must not silently move any of
    those ties.
    """
    x_third = NS_W / 3.0
    y_third = NS_L / 3.0
    # Exactly on the low-x boundary -> middle column, not the west column.
    assert zone_for_point(x_third, NS_L / 2, NS_W, NS_L, 0.0) == "C"
    assert zone_for_point(x_third - 0.01, NS_L / 2, NS_W, NS_L, 0.0) == "W"
    # Exactly on the high-x boundary -> east column, NOT the middle column.
    assert zone_for_point(2 * x_third, NS_L / 2, NS_W, NS_L, 0.0) == "E"
    assert zone_for_point(2 * x_third - 0.01, NS_L / 2, NS_W, NS_L, 0.0) == "C"
    # Exactly on the high-y boundary -> middle row, not the north row.
    assert zone_for_point(NS_W / 2, 2 * y_third, NS_W, NS_L, 0.0) == "C"
    assert zone_for_point(NS_W / 2, 2 * y_third + 0.01, NS_W, NS_L, 0.0) == "N"
    # Exactly on the low-y boundary -> south row, NOT the middle row.
    assert zone_for_point(NS_W / 2, y_third, NS_W, NS_L, 0.0) == "S"
    assert zone_for_point(NS_W / 2, y_third + 0.01, NS_W, NS_L, 0.0) == "C"


def test_band_boundary_ties_diverge_when_the_third_is_not_representable():
    """The historical-tie equivalence is exact only in exact arithmetic.

    ``zone_for_point`` recomputes the comparison in normalized space
    (``(y - L/2) / L`` against ``1/6``) instead of comparing ``y`` against
    ``2 * L / 3`` directly. Where the plot's third is binary-representable the
    two agree bit for bit — 9.0/3 == 3.0 and 15.0/3 == 5.0 are exact, which is
    why ``NS`` preserves all four ties above. Where it is not, a point sitting
    on the *exact float* boundary can round to the other side.

    Measured against the ``405cdb9`` bucketing, ``SQ`` (10x10) is such a plot:
    at ``y == 2 * (L / 3) == 6.666666666666667`` the old code said ``C`` and the
    new one says ``N``. This is pinned rather than hidden because ``NS`` is the
    one fixture on which this property cannot fail, so the test above could
    never see it.

    The divergence is deliberately not "fixed": it is measure-zero (a centroid
    would have to land on that exact float, unreachable from the 0.05 m solver
    grid) and chasing bit-exact parity with the superseded comparison would cost
    more than it buys. The x-axis ties on ``SQ`` do survive, and are pinned too
    so a change of behaviour on either axis shows up.
    """
    x_third = SQ_W / 3.0
    y_third = SQ_L / 3.0
    # Both column ties still match the historical buckets on 10x10.
    assert zone_for_point(x_third, SQ_L / 2, SQ_W, SQ_L, 0.0) == "C"
    assert zone_for_point(2 * x_third, SQ_L / 2, SQ_W, SQ_L, 0.0) == "E"
    # Low-y tie still matches; high-y tie is the one that rounds across.
    assert zone_for_point(SQ_W / 2, y_third, SQ_W, SQ_L, 0.0) == "S"
    assert zone_for_point(SQ_W / 2, 2 * y_third, SQ_W, SQ_L, 0.0) == "N"  # was "C"
    # A hair either side of it is unambiguous and unaffected.
    assert zone_for_point(SQ_W / 2, 2 * y_third - 0.01, SQ_W, SQ_L, 0.0) == "C"
    assert zone_for_point(SQ_W / 2, 2 * y_third + 0.01, SQ_W, SQ_L, 0.0) == "N"


# ── EXTERNAL COMPASS ANCHOR ────────────────────────────────────────────────
#
# Everything else in this file checks the engine against ``ZONE_GRIDS`` and
# ``ROAD_SIDE_NORTH_ANGLE_DEG`` — data that lives in ``vastu.py``, and from
# which the angles were themselves derived. That is circular: it proves the
# engine and the table agree with *each other*, never that either agrees with a
# compass. It is exactly how the swapped E/W grids survived undetected until
# Task 19 — the tests reproduced the wrong data faithfully.
#
# The expectations below are literals derived from the compass alone. Nothing
# here may be computed from ``ZONE_GRIDS``, ``ROAD_SIDE_NORTH_ANGLE_DEG`` or any
# helper that reads them — reintroducing that would reintroduce the blind spot.
#
# Derivation. Plot geometry puts the road-facing edge at y-min by hard
# convention (``_place_main_entrance``, ``plan_geometry``, ``section_geometry``:
# "the road is always the y-min edge"), x points right in plan view, and
# ``road_side`` names the compass direction that front edge faces. Therefore:
#
#   * the y-min (front) third of the plot is that compass direction's third of
#     the Vastu grid, and the y-max (rear) third is the opposite direction's;
#   * left-to-right order follows from east = north turned 90 deg clockwise, so
#     +x is +y turned 90 deg clockwise.
#
#     road S: +y = N, +x = E  ->  front [SW, S, SE]   rear [NW, N, NE]
#     road N: +y = S, +x = W  ->  front [NE, N, NW]   rear [SE, S, SW]
#     road E: +y = W, +x = N  ->  front [SE, E, NE]   rear [SW, W, NW]
#     road W: +y = E, +x = S  ->  front [NW, W, SW]   rear [NE, E, SE]
#
# Front rows are asserted so a 180 deg error is caught; rear rows so a 90 deg
# error (which preserves neither) is caught as well.

COMPASS_FRONT_ROW: dict[str, list[str]] = {
    "S": ["SW", "S", "SE"],
    "N": ["NE", "N", "NW"],
    "E": ["SE", "E", "NE"],
    "W": ["NW", "W", "SW"],
}

COMPASS_REAR_ROW: dict[str, list[str]] = {
    "S": ["NW", "N", "NE"],
    "N": ["SE", "S", "SW"],
    "E": ["SW", "W", "NW"],
    "W": ["NE", "E", "SE"],
}


def _row_zones(side: str, y_frac: float) -> list[str]:
    """The three zones across a horizontal band of the plot, left to right."""
    angle = north_angle_for_road_side(side)
    return [
        zone_for_point(NS_W * x_frac, NS_L * y_frac, NS_W, NS_L, angle)
        for x_frac in (1 / 6, 3 / 6, 5 / 6)
    ]


@pytest.mark.parametrize("side", ["S", "N", "E", "W"])
def test_road_facing_row_is_that_compass_directions_third(side):
    """The y-min row of a plot must be the third of the direction it faces.

    Compass-anchored: the expected rows are literals (see the derivation above),
    not lookups into ``vastu.py``. This is the test the grid-reproduction suite
    could not be — it fails on a 180 deg error even when engine and table agree
    perfectly with each other.
    """
    assert _row_zones(side, 1 / 6) == COMPASS_FRONT_ROW[side], (
        f"road_side={side!r}: the road-facing (y-min) row must be the {side} "
        f"third of the plot"
    )


@pytest.mark.parametrize("side", ["S", "N", "E", "W"])
def test_rear_row_is_the_opposite_compass_directions_third(side):
    """The y-max row must be the third opposite the road — catches a 90 deg error.

    A 180 deg error swaps front and rear rows, so the front-row test alone
    cannot distinguish it from a 90 deg one; pinning the rear row too makes any
    quarter-turn of the map visible.
    """
    assert _row_zones(side, 5 / 6) == COMPASS_REAR_ROW[side], (
        f"road_side={side!r}: the rear (y-max) row must be the third opposite the road"
    )


# ── road_side -> north_angle_deg mapping, proven against all four grids ─────


# Independently re-derived from the compass, not copied from `vastu.py`:
# `north_angle_deg` is measured clockwise from plot +y to true north, and +y
# points from the road-facing edge into the plot, i.e. opposite `road_side`.
#   road S -> +y = North -> 0 deg;    road E -> +y = West  -> 90 deg
#   road N -> +y = South -> 180 deg;  road W -> +y = East  -> 270 deg
EXPECTED_ROAD_SIDE_ANGLES = {"S": 0.0, "E": 90.0, "N": 180.0, "W": 270.0}


def test_road_side_angles_reproduce_every_grid_cell():
    """For each road side, the derived angle must reproduce that side's grid.

    This is the whole back-compat contract: ``ZONE_GRIDS`` is the pre-existing
    ground truth for the four axis-aligned orientations, and the continuous
    engine has to agree with it at every one of the 9 cells, on a square plot
    *and* on a non-square one.
    """
    checked = 0
    for side, grid in ZONE_GRIDS.items():
        angle = north_angle_for_road_side(side)
        assert angle == EXPECTED_ROAD_SIDE_ANGLES[side], (
            f"road_side {side!r} maps to {angle} deg, expected "
            f"{EXPECTED_ROAD_SIDE_ANGLES[side]} deg"
        )
        for plot_w, plot_l in ((SQ_W, SQ_L), (NS_W, NS_L)):
            for row in range(3):
                for col in range(3):
                    x, y = _cell_centre(row, col, plot_w, plot_l)
                    got = zone_for_point(x, y, plot_w, plot_l, angle)
                    assert got == grid[row][col], (
                        f"road_side {side!r} ({angle} deg) on "
                        f"{plot_w}x{plot_l}: cell[{row}][{col}] at ({x}, {y}) "
                        f"gave {got!r}, grid says {grid[row][col]!r}"
                    )
                    checked += 1
    assert checked == len(ZONE_GRIDS) * 2 * 9 == 72


def test_get_zone_delegates_to_zone_for_point():
    """One engine, not two: the legacy wrapper must not be able to disagree."""
    checked = 0
    for side in ("S", "N", "E", "W"):
        angle = north_angle_for_road_side(side)
        for row in range(3):
            for col in range(3):
                x, y = _cell_centre(row, col, NS_W, NS_L)
                assert _get_zone(x, y, NS_W, NS_L, side) == zone_for_point(
                    x, y, NS_W, NS_L, angle
                )
                checked += 1
    assert checked == 36


def test_unknown_road_side_still_falls_back_to_south():
    """``PlotConfig.road_side`` is an unvalidated ``str``; garbage must not raise."""
    assert north_angle_for_road_side("banana") == 0.0
    assert north_angle_for_road_side("") == 0.0
    assert _get_zone(1.0, 1.0, NS_W, NS_L, "X") == _get_zone(1.0, 1.0, NS_W, NS_L, "S")


def test_road_side_is_case_insensitive():
    assert north_angle_for_road_side("e") == north_angle_for_road_side("E") == 90.0


# ── rotation semantics ──────────────────────────────────────────────────────


def test_ninety_degree_rotation_sends_the_ne_corner_to_nw():
    """``north_angle_deg`` is measured CLOCKWISE from plot +y to true north.

    At 90 deg true north points along +x, so the plot's +x/+y corner — which
    sits 45 deg clockwise of plot-north — ends up 45 deg *anticlockwise* of true
    north, i.e. NW. Equivalently: 90 deg must reproduce ``road_side="E"`` (a
    plot whose front faces East has North along +x), whose grid puts "NW" in the
    rear-right cell.
    """
    for plot_w, plot_l in ((SQ_W, SQ_L), (NS_W, NS_L)):
        assert zone_for_point(0.9 * plot_w, 0.9 * plot_l, plot_w, plot_l, 90.0) == "NW"
        assert zone_for_point(0.1 * plot_w, 0.1 * plot_l, plot_w, plot_l, 90.0) == "SE"


def test_ninety_degrees_on_a_non_square_plot_keeps_four_distinct_corners():
    """A 90 deg rotation on a 9x15 plot keeps four distinct corner zones.

    Measured, not assumed: at a 1.67 aspect ratio a metric-space rotation still
    yields four distinct corners, so what it gets wrong here is the *direction*
    (it produces the 270 deg grid where the 90 deg one is required), which the
    second half of this test pins. Outright corner collapse needs a taller plot
    — see `test_high_aspect_corners_do_not_collapse_onto_edges`.
    """
    corners = {
        "rear-right": (0.95 * NS_W, 0.95 * NS_L),
        "rear-left": (0.05 * NS_W, 0.95 * NS_L),
        "front-right": (0.95 * NS_W, 0.05 * NS_L),
        "front-left": (0.05 * NS_W, 0.05 * NS_L),
    }
    zones = {
        name: zone_for_point(x, y, NS_W, NS_L, 90.0) for name, (x, y) in corners.items()
    }
    assert set(zones.values()) == {"NW", "SW", "NE", "SE"}, zones
    # And it agrees corner-for-corner with the grid for the road side whose
    # north angle is 90 deg — road_side="E" (see EXPECTED_ROAD_SIDE_ANGLES).
    assert zones["rear-right"] == ZONE_GRIDS["E"][0][2]
    assert zones["rear-left"] == ZONE_GRIDS["E"][0][0]
    assert zones["front-right"] == ZONE_GRIDS["E"][2][2]
    assert zones["front-left"] == ZONE_GRIDS["E"][2][0]


def test_high_aspect_corners_do_not_collapse_onto_edges():
    """On a 6x20 plot at 45 deg, all four corners must still be distinguishable.

    This is the case where a metric-space rotation degenerates outright, not
    just points the wrong way: the rotated y-extent (~+-9.9 m) dwarfs the 2 m
    column bands, so the clamp pins every corner to an outer column and the four
    corners report only two zones (NE, NE, SW, SW — measured). At 45 deg the
    corners of any rectangle face the four cardinals, which is what a
    normalized-space rotation reports.
    """
    pw, pl = 6.0, 20.0
    zones = [
        zone_for_point(0.95 * pw, 0.95 * pl, pw, pl, 45.0),
        zone_for_point(0.05 * pw, 0.95 * pl, pw, pl, 45.0),
        zone_for_point(0.95 * pw, 0.05 * pl, pw, pl, 45.0),
        zone_for_point(0.05 * pw, 0.05 * pl, pw, pl, 45.0),
    ]
    assert zones == ["N", "W", "E", "S"], zones
    assert len(set(zones)) == 4


def test_diagonal_rotation_is_aspect_ratio_independent():
    """At 45 deg the rear-right corner faces due north on ANY aspect ratio.

    This is the assertion a square-only fixture cannot make. In metric space the
    same 9x15 point lands in "NW", because the rotated east-component (~-2.1 m)
    overshoots a west band that is only 1.5 m wide, while the square plot still
    reports "N". Normalized-space rotation gives "N" for both.
    """
    sq = zone_for_point(0.95 * SQ_W, 0.95 * SQ_L, SQ_W, SQ_L, 45.0)
    ns = zone_for_point(0.95 * NS_W, 0.95 * NS_L, NS_W, NS_L, 45.0)
    assert sq == "N"
    assert ns == "N", (
        f"a 9x15 plot reported {ns!r} for its rear-right corner at 45 deg while "
        "a 10x10 plot reported 'N' — the rotation is being done in metric space, "
        "so zone bands scale with the plot's aspect ratio"
    )


def test_off_axis_angle_is_not_snapped_to_a_cardinal_orientation():
    """An SSE-facing plot must not silently collapse to due S.

    Uses the midpoint of the plot's rear edge, not a corner: a corner sits in the
    middle of a 62.8°-wide diagonal band, so it survives a 22.5° rotation without
    changing zone and would make this test pass on a 4-way snapping engine too.
    """
    for plot_w, plot_l in ((SQ_W, SQ_L), (NS_W, NS_L)):
        x, y = 0.5 * plot_w, 0.95 * plot_l
        a = zone_for_point(x, y, plot_w, plot_l, 157.5)
        b = zone_for_point(x, y, plot_w, plot_l, 180.0)
        assert a in ALL_ZONES
        assert a != b, (
            f"on {plot_w}x{plot_l} a 157.5 deg north angle was bucketed "
            f"identically to 180 deg ({a!r}) — the engine is still snapping to "
            "4 discrete orientations"
        )


def test_zone_never_contradicts_the_compass_bearing():
    """Sweep a full turn: the reported zone may never face the wrong way.

    The rear-right corner sits 45 deg clockwise of plot-north, so at a north
    angle of ``t`` its compass bearing is ``45 - t``. Whichever quadrant that
    bearing lands in, the zone letters must not contain the opposing cardinal
    (a bearing in the NE quadrant can never be reported as anything containing
    "S" or "W"). Angles are chosen off the octant boundaries so every bearing is
    strictly inside a quadrant.
    """
    quadrant_zones = {
        0: {"N", "NE", "E"},  # bearing 0-90
        1: {"E", "SE", "S"},  # 90-180
        2: {"S", "SW", "W"},  # 180-270
        3: {"W", "NW", "N"},  # 270-360
    }
    observed: set[str] = set()
    checked = 0
    for t in range(0, 360, 10):
        bearing = (45.0 - t) % 360.0
        assert bearing % 90.0 != 0.0, "angle sweep must avoid quadrant boundaries"
        allowed = quadrant_zones[int(bearing // 90.0)]
        zone = zone_for_point(0.95 * NS_W, 0.95 * NS_L, NS_W, NS_L, float(t))
        assert zone in allowed, (
            f"north_angle={t} deg puts the rear-right corner at compass bearing "
            f"{bearing} deg, but the engine reported {zone!r} (allowed: "
            f"{sorted(allowed)})"
        )
        observed.add(zone)
        checked += 1
    assert checked == 36
    assert len(observed) == 8, (
        f"a full turn produced only {sorted(observed)} — a continuous rotation "
        "must visit all 8 non-centre zones"
    )


def test_negative_and_wrapped_angles_agree():
    for plot_w, plot_l in ((SQ_W, SQ_L), (NS_W, NS_L)):
        x, y = 0.8 * plot_w, 0.7 * plot_l
        base = zone_for_point(x, y, plot_w, plot_l, 30.0)
        assert zone_for_point(x, y, plot_w, plot_l, 390.0) == base
        assert zone_for_point(x, y, plot_w, plot_l, -330.0) == base


# ── zone_distribution ───────────────────────────────────────────────────────


def _room(x: float, y: float, w: float, d: float) -> Room:
    return Room(id="r", name="R", type="bedroom", x=x, y=y, width=w, depth=d)


def test_zone_distribution_is_area_weighted_and_normalised():
    """A room straddling the NE/N boundary reports membership in both."""
    r = _room(5.5, 7.0, 3.0, 2.0)  # x 5.5-8.5 straddles the x=6.667 boundary
    dist = zone_distribution(r, SQ_W, SQ_L, 0.0)
    assert abs(sum(dist.values()) - 1.0) < 1e-6
    assert set(dist) == {"N", "NE"}, dist
    assert all(0.0 <= v <= 1.0 for v in dist.values())
    # Area weighting, not centroid: 1.167 m of the 3 m width is in N.
    assert dist["N"] == pytest.approx(1.1666 / 3.0, abs=0.02)
    assert dist["NE"] == pytest.approx(1.8333 / 3.0, abs=0.02)


def test_zone_distribution_reports_the_minority_zone_a_centroid_lookup_would_lose():
    """The centroid sits in NE; a third of the floor area is in N and must show up."""
    r = _room(6.0, 7.0, 2.0, 2.0)  # x 6.0-8.0, boundary at 6.667
    assert zone_for_point(r.x + r.width / 2, r.y + r.depth / 2, SQ_W, SQ_L, 0.0) == "NE"
    dist = zone_distribution(r, SQ_W, SQ_L, 0.0)
    assert dist["N"] == pytest.approx(1.0 / 3.0, abs=0.03)
    assert dist["NE"] == pytest.approx(2.0 / 3.0, abs=0.03)


def test_zone_distribution_of_a_fully_contained_room_is_single_zone():
    r = _room(8.0, 8.0, 1.0, 1.0)
    assert zone_distribution(r, SQ_W, SQ_L, 0.0) == pytest.approx({"NE": 1.0})


def test_zone_distribution_follows_the_rotation():
    """The same room reports a different zone mix once north moves."""
    r = _room(6.0, 11.0, 2.0, 3.0)  # rear-right on the 9x15 plot
    unrotated = zone_distribution(r, NS_W, NS_L, 0.0)
    rotated = zone_distribution(r, NS_W, NS_L, 180.0)
    assert abs(sum(rotated.values()) - 1.0) < 1e-6
    assert set(unrotated) == {"NE"}
    assert set(rotated) == {"SW"}


def test_zone_distribution_spans_four_zones_at_the_plot_centre():
    """A room over the Brahmasthan corner junction must report all four cells."""
    r = _room(NS_W / 3 - 0.5, NS_L / 3 - 0.5, 1.0, 1.0)
    dist = zone_distribution(r, NS_W, NS_L, 0.0)
    assert set(dist) == {"SW", "S", "W", "C"}, dist
    assert abs(sum(dist.values()) - 1.0) < 1e-6


def test_zone_distribution_uses_depth_not_width_for_the_y_axis():
    """A wide, shallow room must be sampled over its own depth.

    Every other room in this file is square or is clipped by a band far enough
    away that swapping `depth` for `width` in the y sweep changes nothing. This
    one straddles a row boundary at its midline, so the row split is exactly
    50/50 only if the sweep spans y=4..6; sweeping y=4..10 instead (width used
    for both axes) drops the south row to a sixth.
    """
    r = _room(1.0, 4.0, 6.0, 2.0)  # 9x15 plot: row boundary at y=5
    dist = zone_distribution(r, NS_W, NS_L, 0.0)
    assert set(dist) == {"SW", "S", "SE", "W", "C", "E"}, dist
    south_row = dist["SW"] + dist["S"] + dist["SE"]
    assert south_row == pytest.approx(0.5, abs=0.02), dist


def test_zone_distribution_samples_cell_midpoints():
    """A single sample must land on the room's centroid, not on its low corner.

    The lattice uses the midpoint rule (`(i + 0.5) / samples`). Dropping the
    half-cell offset biases every distribution toward the room's low-x/low-y
    side; at `samples=1` it degenerates to reading the corner. This room's
    corner sits in C while its centroid sits in NE.
    """
    r = _room(6.0, 6.0, 2.0, 2.0)
    assert zone_for_point(6.0, 6.0, SQ_W, SQ_L, 0.0) == "C"
    assert zone_for_point(7.0, 7.0, SQ_W, SQ_L, 0.0) == "NE"
    assert zone_distribution(r, SQ_W, SQ_L, 0.0, samples=1) == {"NE": 1.0}


def test_zone_distribution_sample_count_does_not_change_normalisation():
    r = _room(5.5, 7.0, 3.0, 2.0)
    for samples in (4, 17, 40, 61):
        dist = zone_distribution(r, SQ_W, SQ_L, 0.0, samples=samples)
        assert abs(sum(dist.values()) - 1.0) < 1e-6, samples
        assert set(dist) == {"N", "NE"}, samples


# ── check_vastu wiring ──────────────────────────────────────────────────────


def _cfg(**kw) -> PlotConfig:
    base = dict(
        plot_y_extent=NS_L,
        plot_x_extent=NS_W,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=0.9,
        setback_right=0.9,
        num_bedrooms=2,
        toilets=2,
        parking=False,
        vastu_enabled=True,
    )
    base.update(kw)
    return PlotConfig(**base)


def _layout(rooms: list[Room]) -> Layout:
    return Layout(
        id="X",
        name="Layout X",
        ground_floor=FloorPlan(floor=0, floor_type="ground", rooms=rooms),
        first_floor=FloorPlan(floor=1, floor_type="first", rooms=[]),
        compliance=ComplianceResult(passed=True),
    )


def test_plot_config_north_angle_defaults_to_unset():
    assert _cfg().north_angle_deg is None


def test_check_vastu_uses_north_angle_when_set():
    """A pooja room in the plot's rear-right is NE by road_side, SW once rotated."""
    pooja = Room(
        id="p", name="Pooja Room", type="pooja", x=6.0, y=11.0, width=2.0, depth=3.0
    )
    layout = _layout([pooja])

    _v, warn_default = check_vastu(layout, _cfg(road_side="S"), road_side="S")
    assert not [w for w in warn_default if "Ishanya" in w]

    _v, warn_rotated = check_vastu(
        layout, _cfg(road_side="S", north_angle_deg=180.0), road_side="S"
    )
    pooja_warnings = [w for w in warn_rotated if "Ishanya" in w]
    assert len(pooja_warnings) == 1
    assert "SW zone" in pooja_warnings[0]


def test_check_vastu_falls_back_to_road_side_when_north_angle_unset():
    pooja = Room(
        id="p", name="Pooja Room", type="pooja", x=6.0, y=11.0, width=2.0, depth=3.0
    )
    layout = _layout([pooja])
    _v, warnings = check_vastu(layout, _cfg(road_side="N"), road_side="N")
    pooja_warnings = [w for w in warnings if "Ishanya" in w]
    assert len(pooja_warnings) == 1
    assert "SW zone" in pooja_warnings[0]


def test_check_vastu_north_angle_zero_is_distinct_from_unset():
    """An explicit 0.0 means 'plot +y is true north' and overrides road_side."""
    pooja = Room(
        id="p", name="Pooja Room", type="pooja", x=6.0, y=11.0, width=2.0, depth=3.0
    )
    layout = _layout([pooja])
    _v, warnings = check_vastu(
        layout, _cfg(road_side="N", north_angle_deg=0.0), road_side="N"
    )
    assert not [w for w in warnings if "Ishanya" in w]


# ── guard: the fixtures themselves are non-degenerate ───────────────────────


def test_fixture_plots_are_not_both_square():
    assert SQ_W == SQ_L
    assert not math.isclose(NS_W, NS_L), (
        "the non-square fixture must stay non-square — a square plot cannot "
        "distinguish metric-space from normalized-space rotation"
    )
