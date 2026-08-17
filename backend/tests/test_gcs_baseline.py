"""GCS regression baseline — Task 9D.

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

Regenerate deliberately — never silently — with, from `backend/`:
    uv run python tests/test_gcs_baseline.py --update-baseline
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
        drawing = build_floor_drawing(fp, cfg)
        gcs = compute_gcs(fp, cfg)
        out[name] = {
            "cfg": asdict(cfg),
            "geometry": _floor_to_dict(fp),
            "baseline": {
                **gcs.as_dict(),
                "column_count": len(drawing.columns),
                "frozen_input_column_count": len(fp.columns),
            },
        }
    return out


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


def test_fixture_covers_every_case() -> None:
    """Guards against a case being silently dropped from the fixture."""
    fixture = _require_fixture()
    assert set(fixture) == set(_CASES)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()
    if not args.update_baseline:
        parser.error("pass --update-baseline to (re)generate the fixture")
    fixture = _generate_fixture()
    _FIXTURE_PATH.write_text(json.dumps(fixture, indent=2) + "\n")
    for name, case in fixture.items():
        print(name, case["baseline"])
    print(f"wrote {_FIXTURE_PATH}")
