"""Map real column positions onto footing type + size, joining the layout's
actual column grid (real x,y) against structapi's data.footings (keyed by
corner/edge/interior classification -- see app/engine/pdf.py::_column_class,
which this reuses for classification parity).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.engine.cad_elements import ColumnMarker, WallSegment
from app.engine.pdf import _cluster, _column_class, _nearest_index


@dataclass
class PlacedFooting:
    cx: float
    cy: float
    footing_type: str
    length_m: float
    width_m: float


def place_footings(
    columns: list[ColumnMarker],
    walls: list[WallSegment],
    footings_data: dict,
) -> list[PlacedFooting]:
    """footings_data: structural_design["structapi"]["data"]["footings"],
    keyed "corner"/"edge"/"interior" -> {"data": {"L_m":, "B_m":, ...}, ...}.
    """
    xs = _cluster(
        sorted(
            {w.x1 for w in walls if abs(w.x1 - w.x2) < 1e-9}
            | {w.x2 for w in walls if abs(w.x1 - w.x2) < 1e-9}
        )
    )
    ys = _cluster(
        sorted(
            {w.y1 for w in walls if abs(w.y1 - w.y2) < 1e-9}
            | {w.y2 for w in walls if abs(w.y1 - w.y2) < 1e-9}
        )
    )

    placed = []
    for col in columns:
        idx = _nearest_index(xs, col.cx)
        jdx = _nearest_index(ys, col.cy)
        ftype = _column_class(idx, len(xs), jdx, len(ys))
        fd = (footings_data.get(ftype) or {}).get("data") or {}
        placed.append(
            PlacedFooting(
                cx=col.cx,
                cy=col.cy,
                footing_type=ftype,
                length_m=fd.get("L_m", 0.0),
                width_m=fd.get("B_m", 0.0),
            )
        )
    return placed
