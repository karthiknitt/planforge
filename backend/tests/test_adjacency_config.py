"""D1: solver and scorer must share ONE config-driven adjacency table."""

import json
from pathlib import Path

from app.engine.scorer import _ADJACENCY_PAIRS as SCORER_PAIRS
from app.engine.solver import _ADJACENCY_PAIRS as SOLVER_PAIRS

CONFIG = json.loads(
    (
        Path(__file__).parent.parent / "app" / "config" / "adjacency_pairs.json"
    ).read_text()
)


def test_both_modules_use_the_config_table():
    expected = {(p["a"], p["b"]) for p in CONFIG["pairs"]}
    assert {(a, b) for a, b, _ in SOLVER_PAIRS} == expected
    assert {(a, b) for a, b, _ in SCORER_PAIRS} == expected


def test_tables_are_identical():
    assert [(a, b, float(p)) for a, b, p in SOLVER_PAIRS] == [
        (a, b, float(p)) for a, b, p in SCORER_PAIRS
    ]
