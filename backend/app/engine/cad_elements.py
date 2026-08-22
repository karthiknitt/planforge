"""
CAD element geometry classes for PlanForge.

These are pure data containers used by both the PDF renderer and DXF exporter.
All coordinates are in metres (plot coordinate system).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields as dataclass_fields


@dataclass
class WallSegment:
    """A wall segment defined by two endpoints and its thickness.

    In `plan_geometry`-derived drawings the coordinates are the wall
    CENTRELINE; legacy renderers still construct these at room-edge
    coordinates (5 positional args, kind defaulting to "internal").
    """

    x1: float
    y1: float
    x2: float
    y2: float
    thickness: float  # metres
    kind: str = "internal"  # "external" | "internal"
    # Deterministic, topology-derived identity assigned by derive_walls()
    # (plan_geometry._assign_wall_ids). Empty for legacy hand-built segments.
    id: str = ""

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)


@dataclass
class WallJunction:
    """Point where two or more non-collinear wall centrelines meet."""

    x: float
    y: float
    degree: int  # distinct incident arm directions (2=corner, 3=T, 4=cross)


@dataclass
class Opening:
    """A door/window/ventilator cut into a wall, centred at (cx, cy).

    (cx, cy) sits ON the wall centreline; `width` runs along the wall.
    Door fields describe the hinge end and which room the leaf swings into.
    """

    kind: str  # "door" | "window" | "ventilator"
    cx: float
    cy: float
    width: float
    is_horizontal: bool  # True = on a horizontal wall (width runs along x)
    wall_thickness: float
    hinge_x: float = 0.0
    hinge_y: float = 0.0
    swing_into_room_id: str = ""
    swing_cw: bool = True
    is_main: bool = False  # main entrance door (MD) on the road-facing wall
    # Deterministic instance identity: "<host WallSegment.id>#<offset along
    # that wall>", assigned by plan_geometry.assign_opening_ids(). Empty for
    # legacy hand-built openings.
    id: str = ""
    # IS 962 schedule MARK — a CLASS label shared by every same-kind,
    # same-snapped-width opening (D1 = all 900 mm doors), with the main
    # entrance held out as "MD". Assigned by plan_geometry.assign_opening_marks().
    # A mark deliberately groups; an id deliberately does not.
    mark: str = ""


@dataclass
class LabelBox:
    """Room label with pre-fitted text lines (never truncated — a label that
    cannot fit inside its room moves outside with a leader)."""

    room_id: str
    cx: float
    cy: float
    lines: list[str]
    font_pt: float
    leader: tuple[float, float] | None = None  # target point when outside
    rotated: bool = False  # render at 90 deg (slim vertical rooms)


@dataclass
class DimChainEntry:
    start: float  # along-axis position (m)
    end: float
    text: str  # formatted ft-in


@dataclass
class DimChain:
    side: str  # "bottom" | "top" | "left" | "right"
    level: int  # 0=room chain, 1=overall, 2=plot/setback chain
    coord: float  # cross-axis lane position (m, plot coords)
    entries: list[DimChainEntry] = field(default_factory=list)


@dataclass
class StairGeometry:
    room_id: str
    treads: list[tuple[float, float, float, float]]
    break_line: tuple[float, float, float, float]
    arrow: tuple[float, float, float, float]  # tail -> head
    up_label_xy: tuple[float, float]
    tread_count: int


def _rounded(node):
    if isinstance(node, float):
        return round(node, 4)
    if isinstance(node, (list, tuple)):
        return [_rounded(v) for v in node]
    if isinstance(node, dict):
        return {k: _rounded(v) for k, v in node.items()}
    return node


def _take(cls, payload: dict) -> dict:
    """Keep only the keys `cls` knows about — tolerant rehydration."""
    names = {f.name for f in dataclass_fields(cls)}
    return {k: v for k, v in payload.items() if k in names}


def _stair_from_dict(payload: dict | None) -> StairGeometry | None:
    if not payload:
        return None
    return StairGeometry(
        room_id=payload["room_id"],
        treads=[tuple(t) for t in payload.get("treads") or []],
        break_line=tuple(payload["break_line"]),
        arrow=tuple(payload["arrow"]),
        up_label_xy=tuple(payload["up_label_xy"]),
        tread_count=payload["tread_count"],
    )


@dataclass
class SitePolygon:
    """One closed, possibly holed polygon of site ground, in plot metres."""

    exterior: list[tuple[float, float]]
    holes: list[list[tuple[float, float]]] = field(default_factory=list)


@dataclass
class SiteContext:
    """Ground/site-level entities shared by every renderer (Phase 7 / T32).

    Until this landed, the compound wall + gate were derived twice (PDF
    wrapper + DXF caller over geometry.compound_wall_segments) and the two
    ground-region hatches DISAGREED: the PDF hatched the legal setback
    margin (plot − buildable) while the DXF hatched the open terrace
    (plot − footprint). Both regions live here, named, so each renderer
    projects instead of deriving. `gate_cx` aligns the road-side gate to
    the ground floor's main entrance; None means "centre it"
    (compound_wall_segments' own default) for self-contained single-floor
    builds with no layout context.
    """

    compound_wall_segments: list[tuple[float, float, float, float]] = field(
        default_factory=list
    )
    gate_posts: list[tuple[float, float]] = field(default_factory=list)  # 0 or 2
    gate_cx: float | None = None
    setback_margin: list[SitePolygon] = field(default_factory=list)
    open_terrace: list[SitePolygon] = field(default_factory=list)


@dataclass
class FloorDrawing:
    """Complete canonical drawing for one floor — the single source every
    renderer (PDF/DXF/SVG) projects."""

    floor: int
    walls: list[WallSegment]
    openings: list[Opening]
    columns: list[ColumnMarker]
    junctions: list[WallJunction]
    dim_chains: list[DimChain]
    labels: list[LabelBox]
    stair: StairGeometry | None
    bounds: tuple[float, float, float, float]  # buildable bbox
    diagnostics: list[str] = field(default_factory=list)  # placement problems
    entrance_not_on_ground_floor: bool = False
    # Site entities, shared by every renderer (Task 32). Optional per the
    # Global Constraints: v1 payloads and hand-built drawings carry None.
    site: SiteContext | None = None

    def to_dict(self) -> dict:
        from dataclasses import asdict

        payload = _rounded(asdict(self))
        payload["version"] = 2
        return payload

    @classmethod
    def from_dict(cls, payload: dict) -> FloorDrawing:
        """Rehydrate a to_dict() payload of any stored version.

        Follows LayoutScore's optional-with-default pattern (models.py): every
        field added after v1 — wall/opening ids, opening marks, and later the
        site-context and fixture entities — has a default, so a stored v1
        payload (revision snapshots taken before Phase 7) deserialises and
        renders unchanged. Unknown keys are ignored so future payloads stay
        loadable here.
        """
        site_payload = payload.get("site")
        site = (
            SiteContext(
                compound_wall_segments=[
                    tuple(seg)
                    for seg in site_payload.get("compound_wall_segments") or []
                ],
                gate_posts=[tuple(p) for p in site_payload.get("gate_posts") or []],
                gate_cx=site_payload.get("gate_cx"),
                setback_margin=[
                    SitePolygon(
                        exterior=[tuple(pt) for pt in p.get("exterior") or []],
                        holes=[
                            [tuple(pt) for pt in ring] for ring in p.get("holes") or []
                        ],
                    )
                    for p in site_payload.get("setback_margin") or []
                ],
                open_terrace=[
                    SitePolygon(
                        exterior=[tuple(pt) for pt in p.get("exterior") or []],
                        holes=[
                            [tuple(pt) for pt in ring] for ring in p.get("holes") or []
                        ],
                    )
                    for p in site_payload.get("open_terrace") or []
                ],
            )
            if site_payload is not None
            else None
        )
        return cls(
            floor=payload["floor"],
            bounds=tuple(payload.get("bounds") or (0.0, 0.0, 0.0, 0.0)),
            diagnostics=list(payload.get("diagnostics") or []),
            entrance_not_on_ground_floor=bool(
                payload.get("entrance_not_on_ground_floor", False)
            ),
            site=site,
            walls=[
                WallSegment(**_take(WallSegment, w)) for w in payload.get("walls") or []
            ],
            openings=[
                Opening(**_take(Opening, o)) for o in payload.get("openings") or []
            ],
            columns=[
                ColumnMarker(**_take(ColumnMarker, c))
                for c in payload.get("columns") or []
            ],
            junctions=[
                WallJunction(**_take(WallJunction, j))
                for j in payload.get("junctions") or []
            ],
            dim_chains=[
                DimChain(
                    **{
                        **_take(DimChain, d),
                        "entries": [
                            DimChainEntry(**_take(DimChainEntry, e))
                            for e in d.get("entries") or []
                        ],
                    }
                )
                for d in payload.get("dim_chains") or []
            ],
            labels=[
                LabelBox(**_take(LabelBox, lb)) for lb in payload.get("labels") or []
            ],
            stair=_stair_from_dict(payload.get("stair")),
        )


@dataclass
class ColumnMarker:
    """300×300 mm structural column."""

    cx: float
    cy: float
    size: float = 0.3  # metres
