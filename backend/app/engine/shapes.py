"""Rectilinear room shapes as unions of axis-aligned rectangles.

A rectilinear polygon (L, T, U) is a union of rectangles, so CP-SAT's
add_no_overlap_2d — which operates on intervals, i.e. rectangles — still
applies once it runs over *parts* rather than *rooms*. That is the whole
reason this representation was chosen over arbitrary polygons; see
docs/superpowers/specs/solver_capability_gaps.md section 5.

This module must not import from `models.py`: `Room` depends on it, not the
other way round.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

ShapeTemplate = Literal["RECT", "L", "T", "U"]

SHAPE_TEMPLATES: frozenset[str] = frozenset(get_args(ShapeTemplate))

MIN_RATIO = 0.25
MAX_RATIO = 0.85


@dataclass(frozen=True)
class Rect:
    """One axis-aligned occupied rectangle of a room's footprint."""

    x: float
    y: float
    width: float
    depth: float

    @property
    def area(self) -> float:
        """Unrounded on purpose: callers summing parts round once at the end.

        Rounding here as well would double-round — round(round(w*d, 4), 2)
        differs from round(w*d, 2) for ~0.5% of dimensions, which would move a
        plain RECT room's reported area by 1 cm2 versus the pre-template
        behaviour. RECT parity is the load-bearing property of this module.
        """
        return self.width * self.depth


def union_bbox(parts: tuple[Rect, ...]) -> tuple[float, float, float, float]:
    """(min_x, min_y, max_x, max_y) over all parts."""
    if not parts:
        raise ValueError("union_bbox needs at least one part")
    return (
        min(p.x for p in parts),
        min(p.y for p in parts),
        max(p.x + p.width for p in parts),
        max(p.y + p.depth for p in parts),
    )


def validate_shape(template: ShapeTemplate, ratio: float) -> None:
    """Raise ValueError if the template name or its leg ratio is unusable."""
    if template not in SHAPE_TEMPLATES:
        raise ValueError(
            f"unknown shape template {template!r}; expected one of "
            f"{sorted(SHAPE_TEMPLATES)}"
        )
    if template != "RECT" and not (MIN_RATIO <= ratio <= MAX_RATIO):
        raise ValueError(
            f"ratio {ratio} outside [{MIN_RATIO}, {MAX_RATIO}] — a degenerate leg "
            "would make the room non-contiguous or indistinguishable from a RECT"
        )


def parts_for(
    x: float,
    y: float,
    width: float,
    depth: float,
    template: ShapeTemplate,
    ratio: float = 0.6,
) -> tuple[Rect, ...]:
    """Tile a room's bounding box into the parts of its shape template.

    `ratio` is the fraction of the bbox retained by the narrow leg. Parts tile
    (never overlap) and always span the full bbox, so `union_bbox(parts)`
    round-trips to the input rectangle — the solver keeps optimising
    x/y/width/depth and the template only decides which sub-rectangles are
    actually occupied.
    """
    validate_shape(template, ratio)
    if template == "RECT":
        return (Rect(x, y, width, depth),)

    w1 = width * ratio
    d1 = depth * ratio
    if template == "L":
        # Full-width base band + one leg rising on the low-x side.
        return (
            Rect(x, y, width, d1),
            Rect(x, y + d1, w1, depth - d1),
        )
    if template == "T":
        # Full-width base band + a centred stem.
        stem_x = x + (width - w1) / 2.0
        return (
            Rect(x, y, width, d1),
            Rect(stem_x, y + d1, w1, depth - d1),
        )
    if template == "U":
        # Full-width base band + two legs, leaving a central notch.
        leg = (width - w1) / 2.0
        return (
            Rect(x, y, width, d1),
            Rect(x, y + d1, leg, depth - d1),
            Rect(x + width - leg, y + d1, leg, depth - d1),
        )
    # Not an `else` on the U branch: SHAPE_TEMPLATES auto-populates from the
    # ShapeTemplate Literal, so adding a name there would pass validate_shape
    # and then silently render as a U. Fail loudly instead — a new template
    # must add its own branch here.
    raise ValueError(f"unhandled shape template {template!r}")
