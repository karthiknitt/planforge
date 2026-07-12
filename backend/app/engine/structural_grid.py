"""Derive a structural column grid from a generated layout's columns.

PlanForge layouts carry per-floor `columns: [{x, y}]` (metres, plot
coordinates). structapi needs orthogonal grid spacings. Real plans are not
perfectly regular, so we cluster coordinates and report a confidence flag —
the UI surfaces "structural grid needs review" when extraction is fuzzy
(v1 scope per the integration plan).
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: columns within this distance (m) collapse to one grid line
CLUSTER_TOL = 0.30
#: spacings below this (m) are structurally implausible -> low confidence
MIN_SPACING = 1.8
#: spacings above this (m) exceed ordinary RC residential spans
MAX_SPACING = 8.0


@dataclass
class GridExtraction:
    x_spacings_m: list = field(default_factory=list)
    y_spacings_m: list = field(default_factory=list)
    confident: bool = False
    notes: list = field(default_factory=list)


def _cluster(values: list[float]) -> list[float]:
    """Collapse near-equal coordinates into sorted cluster centers."""
    if not values:
        return []
    ordered = sorted(values)
    clusters: list[list[float]] = [[ordered[0]]]
    for v in ordered[1:]:
        if v - clusters[-1][-1] <= CLUSTER_TOL:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return [sum(c) / len(c) for c in clusters]


def extract_grid(columns: list[dict]) -> GridExtraction:
    """columns: [{x, y}, ...] for one floor (typically the ground floor)."""
    out = GridExtraction()
    if len(columns) < 4:
        out.notes.append(
            f"only {len(columns)} columns — need at least a 4-column bay")
        return out

    xs = _cluster([float(c["x"]) for c in columns])
    ys = _cluster([float(c["y"]) for c in columns])
    if len(xs) < 2 or len(ys) < 2:
        out.notes.append("columns do not form at least one bay each way")
        return out

    out.x_spacings_m = [round(b - a, 2) for a, b in zip(xs, xs[1:])]
    out.y_spacings_m = [round(b - a, 2) for a, b in zip(ys, ys[1:])]

    confident = True
    for axis, spacings in (("x", out.x_spacings_m), ("y", out.y_spacings_m)):
        for s in spacings:
            if s < MIN_SPACING or s > MAX_SPACING:
                confident = False
                out.notes.append(
                    f"{axis}-spacing {s} m outside {MIN_SPACING}-{MAX_SPACING} m")
    # grid completeness: a full grid has len(xs)*len(ys) columns
    expected = len(xs) * len(ys)
    if len(columns) < 0.7 * expected:
        confident = False
        out.notes.append(
            f"{len(columns)} columns vs {expected} grid intersections — "
            "irregular layout; grid needs review")
    out.confident = confident
    if not confident:
        out.notes.append("structural grid needs review before relying on "
                         "the design")
    return out
