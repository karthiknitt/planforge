"""GCS regression baseline — Task 9D, extended by Task 9E.

Pins the Geometric Correctness Score (`compute_gcs`, app/quality/ccqs.py) and
its sub-metrics for five `PlotConfig` cases spanning the geometry surfaces
Tasks 1-10 rewrote (room geometry, wall derivation, opening placement, the
buildable envelope) and Tasks 11-33 will keep changing: a plain rectangular
plot, an L-shaped plot, a trapezoid, a setback-heavy small plot, and a
multi-floor plot with ground-floor parking. With no prior baseline, that
rewrite landed with zero drift signal.

Design note — why this test never re-solves:
`tests/CLAUDE.md` is explicit that CP-SAT is not deterministic and a test
needing stable output must never re-solve inside itself. So the fixture
freezes each case's ROOM AND COLUMN POSITIONS (solved once, by
`--update-baseline`, and committed) rather than freezing the GCS score
itself. `compute_gcs()` calls `build_floor_drawing()` internally, which is
NOT frozen — it re-derives walls, openings, labels, dimensions and columns
from the frozen room positions on every test run. That is exactly the
derivation code Tasks 1-10 touched, so a regression there still moves the
score even though the room layout is fixed. Verified empirically (see the
Task 9D report) that this pipeline is bit-for-bit deterministic given a
fixed room list and PlotConfig on this hardware — the same frozen L-shaped
layout scored identically (columns=10, GCS total=80.0, every sub-metric
equal) whether run through `main` or this branch, which is also the
evidence behind the "no column-derivation drift" answer in that report.
Tolerance is therefore 0.0 for every sub-metric: there is no jitter source
left once the room layout is frozen, so any change means a real behaviour
change in the derivation code, not noise.

Task 9E added a second, different thing to the fixture: the DERIVED OPENING
POSITIONS. The sub-metrics above are all quality measures, and a quality
measure is blind to drift by construction — if an entrance at 7.00 m and one
at 7.05 m are both well placed, both score full marks. Task 9D's review
proved the point: nudging the main entrance 5 cm passed every assertion in
this file. `test_opening_positions_match_baseline` closes that by comparing
the coordinate itself, and
`test_five_cm_main_entrance_shift_fails_the_baseline` is the standing
regression test for the finding.

Regenerate deliberately — never silently — with, from `backend/`:
    uv run python tests/test_gcs_baseline.py --rederive
        Keeps the committed room layouts and recomputes only what is derived
        from them (openings, GCS, column counts). This is what you want
        whenever the DERIVATION or the SCORE changed but the layouts did
        not — it leaves `cfg`/`geometry` byte-identical, so the diff shows
        the behaviour change and nothing else.
    uv run python tests/test_gcs_baseline.py --update-baseline
        Re-solves every case from scratch. CP-SAT is not run-to-run
        deterministic, so this swaps in genuinely different room layouts and
        makes a scoring change indistinguishable from a layout change. Use
        it only when the CASES themselves change.
(The script inserts `backend/` onto `sys.path` itself when run this way,
since running a file directly — unlike `pytest` or `python -m` — does not
put the package root on the path.)
A task that legitimately changes GCS must update this fixture in its own
commit, with the reason in the message.

Blind spot, stated explicitly (see the Task 9D report for the full
reasoning): a `FloorPlan` carries TWO distinct notions of "columns".
`fp.columns` is whatever the SOLVER placed (`solver.py`'s
`_wall_junction_cols` / the archetype fallback's equivalent) — that is
frozen INPUT here, produced by code this test never calls, so a regression
in solver-side column placement is invisible to this baseline. What this
test DOES exercise live, every run, is `derive_columns()`
(`app/engine/plan_geometry.py`) via `build_floor_drawing()` — the
structural-significance filter that turns wall junctions into the columns
`compute_gcs`'s collision check actually scores. That is asserted below as
`column_count`. The frozen `fp.columns` positions are still stored in the
fixture (under "geometry") and asserted for completeness/reviewability —
any future regeneration shows a column-generation change as a fixture diff
— but this test cannot itself detect a column-GENERATION regression, only
a column-DERIVATION one.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

if __name__ == "__main__":
    # Run as a script (not via `pytest` / `python -m`), so `backend/` is not
    # on sys.path the way pytest's rootdir insertion or `-m` would put it.
    # Without this, `--update-baseline` fails with
    # `ModuleNotFoundError: No module named 'app'` before argparse even runs.
    sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from app.engine.cad_elements import Opening
from app.engine.generator import generate
from app.engine.models import Column, FloorPlan, PlotConfig, Room
from app.engine.plan_geometry import build_floor_drawing
from app.quality.ccqs import compute_gcs

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "gcs_baseline.json"

# ── Five cases spanning the geometry surfaces under active rewrite ─────────
_CASES: dict[str, PlotConfig] = {
    "rect_2bhk_g1": PlotConfig(
        plot_length=30.0,
        plot_width=50.0,
        setback_front=3.0,
        setback_rear=2.0,
        setback_left=1.5,
        setback_right=1.5,
        num_bedrooms=2,
        toilets=2,
        parking=True,
        num_floors=2,
    ),
    "l_shaped_3bhk": PlotConfig(
        plot_length=15.0,
        plot_width=12.0,
        setback_front=1.2,
        setback_rear=1.2,
        setback_left=1.0,
        setback_right=1.0,
        num_bedrooms=3,
        toilets=2,
        parking=False,
        plot_shape="l_shaped",
        cutout_corner="NE",
        cutout_width=4.0,
        cutout_height=4.0,
    ),
    "trapezoid_2bhk": PlotConfig(
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
    ),
    "setback_heavy_1bhk": PlotConfig(
        plot_length=12.0,
        plot_width=9.0,
        setback_front=3.0,
        setback_rear=3.0,
        setback_left=2.0,
        setback_right=2.0,
        num_bedrooms=1,
        toilets=1,
        parking=False,
    ),
    # `has_stilt` does not currently gate layout generation anywhere in
    # app/engine (only referenced in models.py + compliance.py's FAR calc,
    # confirmed on both main and this branch) — num_floors=3 also caps at 2
    # floors from generate() on both branches (a pre-existing generator
    # limit, not a Task 1-10 regression). This case therefore scores what
    # num_floors=3 + has_stilt=True actually produces today: a ground floor
    # carrying parking alongside living rooms, not a dedicated stilt floor.
    # That is the honest current behaviour, not the aspirational one.
    "g2_stilt_parking": PlotConfig(
        plot_length=20.0,
        plot_width=15.0,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=1.0,
        setback_right=1.0,
        num_bedrooms=4,
        toilets=3,
        parking=True,
        num_floors=3,
        has_stilt=True,
    ),
}


def _floor_to_dict(fp: FloorPlan) -> dict[str, Any]:
    return {
        "floor": fp.floor,
        "floor_type": fp.floor_type,
        "rooms": [
            {
                "id": r.id,
                "name": r.name,
                "type": r.type,
                "x": r.x,
                "y": r.y,
                "width": r.width,
                "depth": r.depth,
            }
            for r in fp.rooms
        ],
        "columns": [{"x": c.x, "y": c.y} for c in fp.columns],
    }


def _floor_from_dict(d: dict[str, Any]) -> FloorPlan:
    return FloorPlan(
        floor=d["floor"],
        floor_type=d["floor_type"],
        rooms=[
            Room(
                id=r["id"],
                name=r["name"],
                type=r["type"],
                x=r["x"],
                y=r["y"],
                width=r["width"],
                depth=r["depth"],
            )
            for r in d["rooms"]
        ],
        columns=[Column(x=c["x"], y=c["y"]) for c in d["columns"]],
    )


def _opening_records(openings: list[Opening]) -> list[dict[str, Any]]:
    """Freeze each derived opening's POSITION, not just its existence.

    GCS scores openings for presence, collision and (as of Task 9E)
    buildable clearance — all of which a 5 cm shift of a well-placed door
    passes untouched. Only comparing the derived coordinate against a frozen
    expected value catches that kind of drift, so this is deliberately a
    coordinate freeze and not another quality measure.

    Rounded to 0.1 mm (far below any real placement change, far above float
    noise) and sorted, so the comparison does not also pin the order
    `build_floor_drawing` happens to emit openings in.
    """
    records = [
        {
            "kind": op.kind,
            "cx": round(op.cx, 4),
            "cy": round(op.cy, 4),
            "width": round(op.width, 4),
            "is_horizontal": op.is_horizontal,
            "is_main": op.is_main,
        }
        for op in openings
    ]
    return sorted(records, key=lambda r: (r["kind"], r["cx"], r["cy"], r["width"]))


def _opening_mismatches(
    actual: list[dict[str, Any]], expected: list[dict[str, Any]]
) -> list[str]:
    """Every way `actual` differs from the frozen `expected`, as messages.

    Factored out of the assertion so the 5 cm regression test below can feed
    it a deliberately perturbed input and prove it actually fires.
    """
    messages: list[str] = []
    if len(actual) != len(expected):
        messages.append(f"opening count {len(actual)} != baseline {len(expected)}")
    for i, (a, e) in enumerate(zip(actual, expected)):
        if a != e:
            messages.append(f"opening[{i}] {a} != baseline {e}")
    return messages


def _load_fixture() -> dict[str, Any] | None:
    try:
        return json.loads(_FIXTURE_PATH.read_text())
    except FileNotFoundError:
        return None


def _generate_fixture() -> dict[str, Any]:
    """Solve each case once (CP-SAT — not deterministic run to run) and
    freeze the resulting room/column positions plus the GCS baseline they
    score today. Only invoked from the --update-baseline CLI, never from a
    test."""
    out: dict[str, Any] = {}
    for name, cfg in _CASES.items():
        layouts = generate(cfg)
        assert layouts, f"{name}: solver produced no layouts at all"
        fp = layouts[0].ground_floor
        assert fp is not None and fp.rooms, f"{name}: ground floor has no rooms"
        out[name] = {
            "cfg": asdict(cfg),
            "geometry": _floor_to_dict(fp),
            **_derived_expectations(fp, cfg),
        }
    return out


def _derived_expectations(fp: FloorPlan, cfg: PlotConfig) -> dict[str, Any]:
    """Everything the fixture stores that is DERIVED from the frozen room
    layout — recomputed identically by `--update-baseline` (after a fresh
    solve) and `--rederive` (against the committed layout)."""
    drawing = build_floor_drawing(fp, cfg)
    gcs = compute_gcs(fp, cfg)
    return {
        "openings": _opening_records(drawing.openings),
        "baseline": {
            **gcs.as_dict(),
            "column_count": len(drawing.columns),
            "frozen_input_column_count": len(fp.columns),
        },
    }


def _rederive_fixture() -> dict[str, Any]:
    """Recompute the derived expectations against the ALREADY-FROZEN room
    layouts, leaving `cfg` and `geometry` byte-identical.

    This is the right entry point when the derivation or the score changed
    but the layouts did not: `--update-baseline` re-solves, and CP-SAT is not
    run-to-run deterministic, so it would silently swap in different rooms
    and make a scoring change indistinguishable from a layout change.
    """
    fixture = _load_fixture()
    if fixture is None:
        raise SystemExit(f"{_FIXTURE_PATH} does not exist — use --update-baseline")
    return {
        name: {
            "cfg": case["cfg"],
            "geometry": case["geometry"],
            **_derived_expectations(
                _floor_from_dict(case["geometry"]), PlotConfig(**case["cfg"])
            ),
        }
        for name, case in fixture.items()
    }


# ── Tests ────────────────────────────────────────────────────────────────

_FIXTURE = _load_fixture()


def _require_fixture() -> dict[str, Any]:
    if _FIXTURE is None:
        pytest.fail(
            f"{_FIXTURE_PATH} does not exist — generate it from `backend/` with "
            "`uv run python tests/test_gcs_baseline.py --update-baseline`"
        )
    return _FIXTURE


@pytest.mark.parametrize("case_name", sorted(_CASES))
def test_gcs_matches_baseline(case_name: str) -> None:
    fixture = _require_fixture()
    case = fixture[case_name]
    baseline = case["baseline"]
    cfg = PlotConfig(**case["cfg"])
    fp = _floor_from_dict(case["geometry"])

    drawing = build_floor_drawing(fp, cfg)
    result = compute_gcs(fp, cfg)

    # Total: a regression fails, an improvement doesn't (>=, tolerance 0.0 —
    # see module docstring for why no jitter tolerance is needed here).
    assert result.total >= baseline["total"], (
        f"{case_name}: GCS total regressed {result.total} < baseline "
        f"{baseline['total']}"
    )
    # Every sub-metric individually, so a regression names the failing
    # dimension instead of only the aggregate moving.
    assert result.phantom_walls == baseline["phantom_walls"], (
        f"{case_name}: phantom_walls {result.phantom_walls} != baseline "
        f"{baseline['phantom_walls']}"
    )
    assert result.collisions == baseline["collisions"], (
        f"{case_name}: collisions {result.collisions} != baseline "
        f"{baseline['collisions']}"
    )
    assert result.label_overflow == baseline["label_overflow"], (
        f"{case_name}: label_overflow {result.label_overflow} != baseline "
        f"{baseline['label_overflow']}"
    )
    assert result.dimension_coverage_pct == baseline["dimension_coverage_pct"], (
        f"{case_name}: dimension_coverage_pct {result.dimension_coverage_pct} "
        f"!= baseline {baseline['dimension_coverage_pct']}"
    )
    assert result.standard_scale == baseline["standard_scale"], (
        f"{case_name}: standard_scale {result.standard_scale} != baseline "
        f"{baseline['standard_scale']}"
    )
    assert result.doors_per_room_ok == baseline["doors_per_room_ok"], (
        f"{case_name}: doors_per_room_ok {result.doors_per_room_ok} != "
        f"baseline {baseline['doors_per_room_ok']}"
    )
    assert result.windows_per_habitable_ok == baseline["windows_per_habitable_ok"], (
        f"{case_name}: windows_per_habitable_ok "
        f"{result.windows_per_habitable_ok} != baseline "
        f"{baseline['windows_per_habitable_ok']}"
    )
    assert (
        result.opening_clearance_violations == baseline["opening_clearance_violations"]
    ), (
        f"{case_name}: opening_clearance_violations "
        f"{result.opening_clearance_violations} != baseline "
        f"{baseline['opening_clearance_violations']}; reasons: "
        f"{result.debug.get('opening_clearance')}"
    )
    # Column count from the SAME derivation compute_gcs's collision check
    # runs (build_floor_drawing -> derive_columns), not the solver's own
    # raw column list — this is what would move if column derivation
    # regressed. Not part of GcsResult itself, asserted separately.
    assert len(drawing.columns) == baseline["column_count"], (
        f"{case_name}: derived column_count {len(drawing.columns)} != "
        f"baseline {baseline['column_count']}"
    )
    # Pins the frozen INPUT column count too (solver-side placement, not
    # re-derived here — see the module docstring's "blind spot" note). This
    # doesn't detect a column-generation regression by itself, but it makes
    # one visible as a fixture diff on the next --update-baseline run.
    assert len(fp.columns) == baseline["frozen_input_column_count"], (
        f"{case_name}: fixture is internally inconsistent — frozen "
        f"geometry has {len(fp.columns)} columns but baseline recorded "
        f"{baseline['frozen_input_column_count']}"
    )


@pytest.mark.parametrize("case_name", sorted(_CASES))
def test_opening_positions_match_baseline(case_name: str) -> None:
    """Part 1 of Task 9E — drift, not quality.

    Freezing the derived opening coordinates is the only thing that catches
    an opening moving from one perfectly-good place to another.
    """
    fixture = _require_fixture()
    case = fixture[case_name]
    expected = case["openings"]
    assert expected, f"{case_name}: baseline froze no openings at all"

    cfg = PlotConfig(**case["cfg"])
    fp = _floor_from_dict(case["geometry"])
    actual = _opening_records(build_floor_drawing(fp, cfg).openings)

    mismatches = _opening_mismatches(actual, expected)
    assert not mismatches, f"{case_name}: opening positions drifted:\n" + "\n".join(
        mismatches
    )


# `l_shaped_3bhk` derives NO main entrance at all — no `is_main` opening, and
# neither `FloorDrawing.entrance_not_on_ground_floor` nor a diagnostic says
# so. Found while writing the test below (Task 9E); it is a real gap in
# opening derivation, out of scope to fix here, and pinned explicitly by
# `test_main_entrance_count_per_case` so it cannot quietly spread.
_CASES_WITHOUT_MAIN_ENTRANCE = {"l_shaped_3bhk"}
_CASES_WITH_MAIN_ENTRANCE = sorted(set(_CASES) - _CASES_WITHOUT_MAIN_ENTRANCE)
assert _CASES_WITH_MAIN_ENTRANCE, "no case left to run the 5 cm shift test on"


def test_main_entrance_count_per_case() -> None:
    """Guards the exclusion list above. Without this, a case losing its main
    entrance would silently shrink the 5 cm regression test's coverage
    instead of failing."""
    fixture = _require_fixture()
    counts = {
        name: sum(1 for r in fixture[name]["openings"] if r["is_main"])
        for name in sorted(_CASES)
    }
    expected = {
        name: (0 if name in _CASES_WITHOUT_MAIN_ENTRANCE else 1)
        for name in sorted(_CASES)
    }
    assert counts == expected


@pytest.mark.parametrize("case_name", _CASES_WITH_MAIN_ENTRANCE)
def test_five_cm_main_entrance_shift_fails_the_baseline(case_name: str) -> None:
    """Regression test for the hole Task 9D's review found: nudging the main
    entrance 5 cm along its wall passed the entire GCS baseline undetected.
    It must now be caught. Asserts the *detector*, so it stays meaningful
    even when the fixture is legitimately regenerated."""
    fixture = _require_fixture()
    case = fixture[case_name]
    expected = case["openings"]
    assert expected, f"{case_name}: baseline froze no openings at all"

    cfg = PlotConfig(**case["cfg"])
    fp = _floor_from_dict(case["geometry"])
    actual = _opening_records(build_floor_drawing(fp, cfg).openings)

    # Control: unperturbed geometry must be clean, otherwise "the shift was
    # caught" below would prove nothing.
    assert not _opening_mismatches(actual, expected), (
        f"{case_name}: baseline already mismatches before any perturbation"
    )

    mains = [r for r in actual if r["is_main"]]
    assert len(mains) == 1, (
        f"{case_name}: expected exactly one main entrance in the derived "
        f"openings, found {len(mains)}"
    )

    shifted = [dict(r) for r in actual]
    for record in shifted:
        if record["is_main"]:
            axis = "cx" if record["is_horizontal"] else "cy"
            record[axis] = round(record[axis] + 0.05, 4)

    assert _opening_mismatches(shifted, expected), (
        f"{case_name}: shifting the main entrance 5 cm along its own wall was "
        "NOT caught by the baseline comparison"
    )


def test_fixture_covers_every_case() -> None:
    """Guards against a case being silently dropped from the fixture."""
    fixture = _require_fixture()
    assert set(fixture) == set(_CASES)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--update-baseline",
        action="store_true",
        help="re-solve every case (CP-SAT — new room layouts) and refreeze",
    )
    mode.add_argument(
        "--rederive",
        action="store_true",
        help="keep the frozen layouts, recompute only the derived expectations",
    )
    args = parser.parse_args()
    fixture = _rederive_fixture() if args.rederive else _generate_fixture()
    _FIXTURE_PATH.write_text(json.dumps(fixture, indent=2) + "\n")
    for name, case in fixture.items():
        print(name, case["baseline"])
    print(f"wrote {_FIXTURE_PATH}")
