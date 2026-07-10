"""Preferred-adjacency pairs, loaded from config (D1).

Solver and scorer previously kept two separate hardcoded tables with
different contents (solver had kitchen-utility, scorer did not).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).parent.parent / "config" / "adjacency_pairs.json"


@lru_cache(maxsize=1)
def load_adjacency_pairs() -> tuple[tuple[str, str, float], ...]:
    data = json.loads(_PATH.read_text())
    return tuple((p["a"], p["b"], float(p["points"])) for p in data["pairs"])
