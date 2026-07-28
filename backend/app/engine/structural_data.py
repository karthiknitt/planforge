"""Typed structural model assembled from a layout + structapi's design output.

Every sheet in the Structural Drawing Set reads from :class:`StructuralModel`
rather than digging into structapi's nested response dicts. That keeps the
key-format knowledge (and the grid-index arithmetic below) in exactly one
place, and it is what lets independently-written sheet renderers agree on
member marks, positions and sizes.

Two facts about structapi's contract shape everything here:

1. **One framing design serves the whole building.** structapi takes a single
   ``grid`` plus a ``storeys`` count; ``storeys`` only scales BOQ quantities
   and seismic storey weights. Beams are keyed ``(axis, span, tributary)`` and
   slab panels by ``(lx, ly, case)`` — there is no floor discriminator, and
   there should not be: column axial load accumulates down the storeys, so
   splitting the call per floor would under-design the ground-floor columns.
   Per-floor sheets therefore differ by *geometry underlay and level
   annotation*, not by member design. See :class:`FloorFraming`.

2. **Member records carry grid indices, so they are placeable.** Each beam
   group has ``grid_line_indices`` (indices along the perpendicular axis) and
   each slab panel has ``panel_indices`` (``[i, j]`` bay cells). structapi's
   own ``grid_lines.x_coords_m`` starts at 0.0 — it is grid-relative — so the
   plot-space origin has to come from PlanForge's own
   :func:`app.engine.structural_grid.extract_grid`, which is why that function
   retains the absolute cluster centres.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.engine.cad_elements import FloorDrawing
from app.engine.models import FloorPlan, Layout, PlotConfig
from app.engine.pdf import _column_class
from app.engine.plan_geometry import build_floor_drawing
from app.engine.structural_grid import extract_grid

#: footing class -> schedule mark. Mirrors structapi's own corner/edge/
#: interior classification (extreme grid index on both axes / one axis /
#: neither), so a mark on the plan and a row in the schedule always refer to
#: the same designed member.
FOOTING_MARK = {"corner": "T1", "edge": "T2", "interior": "T3"}

#: column class -> schedule mark, same classification as FOOTING_MARK.
COLUMN_MARK = {"corner": "C1", "edge": "C2", "interior": "C3"}


@dataclass(frozen=True)
class GridRef:
    """Absolute structural grid in plot coordinates (metres)."""

    x_lines_m: list[float] = field(default_factory=list)
    y_lines_m: list[float] = field(default_factory=list)
    confident: bool = True
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.x_lines_m) >= 2 and len(self.y_lines_m) >= 2

    def lines(self, axis: str) -> list[float]:
        return self.x_lines_m if axis == "x" else self.y_lines_m

    def extent(self, axis: str) -> tuple[float, float]:
        vals = self.lines(axis)
        return (vals[0], vals[-1]) if vals else (0.0, 0.0)


@dataclass(frozen=True)
class ColumnItem:
    tag: str  # sequential plan tag, e.g. "C7"
    mark: str  # schedule mark by class, e.g. "C1"
    col_class: str  # corner | edge | interior
    cx: float
    cy: float
    b_mm: float
    D_mm: float
    bars: str
    design: dict = field(default_factory=dict)


@dataclass(frozen=True)
class FootingItem:
    mark: str  # T1 | T2 | T3
    footing_class: str
    cx: float
    cy: float
    length_m: float
    width_m: float
    depth_mm: float
    design: dict = field(default_factory=dict)


@dataclass(frozen=True)
class BeamRun:
    """One designed beam group projected onto a grid line."""

    mark: str  # B1.. / PB1..
    axis: str  # "x" (runs along x) | "y"
    ordinate_m: float  # cross-axis position of the run
    start_m: float
    end_m: float
    b_mm: float
    D_mm: float
    span_m: float
    design: dict = field(default_factory=dict)

    @property
    def endpoints(self) -> tuple[float, float, float, float]:
        if self.axis == "x":
            return self.start_m, self.ordinate_m, self.end_m, self.ordinate_m
        return self.ordinate_m, self.start_m, self.ordinate_m, self.end_m


@dataclass(frozen=True)
class SlabPanel:
    mark: str  # S1..
    x1: float
    y1: float
    x2: float
    y2: float
    lx_m: float
    ly_m: float
    kind: str  # "one-way" | "two-way"
    case: str  # structapi panel case (interior/edge/corner variants)
    D_mm: float
    design: dict = field(default_factory=dict)

    @property
    def is_two_way(self) -> bool:
        return self.kind == "two-way"


@dataclass(frozen=True)
class FloorFraming:
    """One framing level: the beams and slab panels *over* a given floor."""

    level_label: str  # e.g. "GF ROOF / FF FLOOR"
    drg_plan: str  # sheet number of its plan sheet
    drg_details: str  # sheet number of its beam-details sheet
    floor_plan: FloorPlan  # the floor *below* this framing level
    drawing: FloorDrawing | None
    beams: list[BeamRun] = field(default_factory=list)
    slabs: list[SlabPanel] = field(default_factory=list)
    is_terrace: bool = False


@dataclass(frozen=True)
class StructuralModel:
    project_name: str
    cfg: PlotConfig
    layout: Layout
    grid: GridRef
    #: ground-floor drawing — the footing/plinth sheets are all set out from
    #: it (its walls carry the plinth beams, its bounds size the grid bubbles)
    gf_drawing: FloorDrawing | None = None
    columns: list[ColumnItem] = field(default_factory=list)
    footings: list[FootingItem] = field(default_factory=list)
    plinth_beams: list[BeamRun] = field(default_factory=list)
    floors: list[FloorFraming] = field(default_factory=list)
    materials: dict = field(default_factory=dict)
    lateral: dict = field(default_factory=dict)
    quantities: dict = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    violations: list[dict] = field(default_factory=list)
    disclaimer: str = ""
    revision_id: Any = None
    status: str = ""
    changelog: list[str] = field(default_factory=list)
    structapi_data: dict = field(default_factory=dict)

    @property
    def layout_label(self) -> str:
        return f"{self.layout.id} - {self.layout.name}" if self.layout else ""

    def columns_by_class(self) -> dict[str, ColumnItem]:
        """One representative column per class, for the details sheet."""
        out: dict[str, ColumnItem] = {}
        for col in self.columns:
            out.setdefault(col.col_class, col)
        return out

    def footings_by_class(self) -> dict[str, FootingItem]:
        out: dict[str, FootingItem] = {}
        for f in self.footings:
            out.setdefault(f.footing_class, f)
        return out


# ── assembly ─────────────────────────────────────────────────────────────────


def _grid_from_layout(layout: Layout) -> GridRef:
    gf = layout.ground_floor
    cols = [{"x": c.x, "y": c.y} for c in (gf.columns or [])] if gf else []
    g = extract_grid(cols)
    return GridRef(
        x_lines_m=list(g.x_lines_m),
        y_lines_m=list(g.y_lines_m),
        confident=g.confident,
        notes=list(g.notes),
    )


def _nearest(vals: list[float], v: float) -> int:
    return min(range(len(vals)), key=lambda i: abs(vals[i] - v))


def _build_columns(
    grid: GridRef, layout: Layout, columns_data: dict
) -> list[ColumnItem]:
    """Classify each real ground-floor column against the grid structapi was
    designed with.

    Deliberately *not* `footing_placement.place_footings`, which clusters wall
    centrelines instead of columns. Wall centrelines and column positions can
    yield different line counts, and the class of a column is its index within
    the grid — so classifying against a different grid than the one structapi
    received can assign a column the wrong designed size. Here the grid is the
    one that was actually designed.
    """
    gf = layout.ground_floor
    if not grid.ok or not gf or not gf.columns:
        return []
    out: list[ColumnItem] = []
    for n, col in enumerate(gf.columns, start=1):
        i = _nearest(grid.x_lines_m, col.x)
        j = _nearest(grid.y_lines_m, col.y)
        cls = _column_class(i, len(grid.x_lines_m), j, len(grid.y_lines_m))
        d = (columns_data.get(cls) or {}) if columns_data else {}
        out.append(
            ColumnItem(
                tag=f"C{n}",
                mark=COLUMN_MARK.get(cls, "C?"),
                col_class=cls,
                cx=col.x,
                cy=col.y,
                b_mm=float(d.get("b_mm", 300.0)),
                D_mm=float(d.get("D_mm", 300.0)),
                bars=str(d.get("bars", "—")),
                design=d,
            )
        )
    return out


def _build_footings(
    columns: list[ColumnItem], footings_data: dict
) -> list[FootingItem]:
    out: list[FootingItem] = []
    for col in columns:
        entry = footings_data.get(col.col_class) or {}
        d = entry.get("data") or {}
        if "L_m" not in d or "B_m" not in d:
            continue
        out.append(
            FootingItem(
                mark=FOOTING_MARK.get(col.col_class, "T?"),
                footing_class=col.col_class,
                cx=col.cx,
                cy=col.cy,
                length_m=float(d["L_m"]),
                width_m=float(d["B_m"]),
                depth_mm=float(d.get("D_overall_mm", 0.0)),
                design=d,
            )
        )
    return out


def assign_marks_by_span(data: dict, prefix: str) -> dict[str, str]:
    """Mark each design group ``B1``/``PB1``… by ascending span."""
    ordered = sorted(data.keys(), key=lambda k: (data[k].get("span_m", 0.0), str(k)))
    return {k: f"{prefix}{i + 1}" for i, k in enumerate(ordered)}


def _build_beam_runs(
    grid: GridRef, beams_data: dict, prefix: str = "B"
) -> list[BeamRun]:
    """Project each structapi beam group onto the grid lines it occupies.

    ``grid_line_indices`` indexes the lines *perpendicular* to the beam's own
    axis: an x-direction beam sits at ``y_lines[line]`` and runs the full
    x-extent of the grid. A group with no indices (older payloads) falls back
    to a single run on line 0 so it still appears on the plan rather than
    vanishing between the schedule and the drawing.
    """
    if not grid.ok or not beams_data:
        return []
    marks = assign_marks_by_span(beams_data, prefix)
    runs: list[BeamRun] = []
    for key, d in beams_data.items():
        axis = str(d.get("axis") or str(key).split("-")[0] or "x")
        axis = "x" if axis not in ("x", "y") else axis
        perp_lines = grid.lines("y" if axis == "x" else "x")
        start_m, end_m = grid.extent(axis)
        indices = d.get("grid_line_indices") or [0]
        for line in indices:
            if not (0 <= int(line) < len(perp_lines)):
                continue
            runs.append(
                BeamRun(
                    mark=marks[key],
                    axis=axis,
                    ordinate_m=perp_lines[int(line)],
                    start_m=start_m,
                    end_m=end_m,
                    b_mm=float(d.get("b_mm", 230.0)),
                    D_mm=float(d.get("D_mm", 380.0)),
                    span_m=float(d.get("span_m", 0.0)),
                    design=d,
                )
            )
    return runs


def _build_slab_panels(grid: GridRef, slabs_data: dict) -> list[SlabPanel]:
    """Expand each designed panel type over the bay cells it covers.

    Panels are bounded by *beams* (grid bays), not by rooms — the room-based
    fallback the old sheet used could label a slab panel that no beam actually
    frames.
    """
    if not grid.ok or not slabs_data:
        return []
    xs, ys = grid.x_lines_m, grid.y_lines_m
    cells: list[tuple[int, int, dict]] = []
    for d in slabs_data.values():
        for idx in d.get("panel_indices") or []:
            if len(idx) != 2:
                continue
            cells.append((int(idx[0]), int(idx[1]), d))
    cells.sort(key=lambda t: (t[1], t[0]))

    out: list[SlabPanel] = []
    for n, (i, j, d) in enumerate(cells, start=1):
        if not (0 <= i < len(xs) - 1 and 0 <= j < len(ys) - 1):
            continue
        out.append(
            SlabPanel(
                mark=f"S{n}",
                x1=xs[i],
                y1=ys[j],
                x2=xs[i + 1],
                y2=ys[j + 1],
                lx_m=float(d.get("lx_m", 0.0)),
                ly_m=float(d.get("ly_m", 0.0)),
                kind=str(d.get("type", "two-way")),
                case=str(d.get("case_", "")),
                D_mm=float(d.get("D_mm", 0.0)),
                design=d,
            )
        )
    return out


def _plinth_runs(walls, plinth_beams_data: dict) -> list[BeamRun]:
    """Plinth beams follow the *wall* layout, not the column grid.

    A plinth beam's job is to carry the wall standing on it down to the
    footings, so it runs wherever a wall runs — which is why
    `plinth_beam_design` groups them by ``(kind, length)`` with no axis or
    grid index. A wall whose group key has no design entry is still emitted,
    unmarked: an unlabelled beam line is honest, a fabricated mark is not.
    """
    if not walls:
        return []
    from app.services.plinth_beam_design import plinth_group_key

    marks = assign_marks_by_span(plinth_beams_data or {}, "PB")
    runs: list[BeamRun] = []
    for w in walls:
        key = plinth_group_key(w.kind, round(w.length, 1))
        d = (plinth_beams_data or {}).get(key) or {}
        horizontal = abs(w.y1 - w.y2) < 1e-9
        axis = "x" if horizontal else "y"
        runs.append(
            BeamRun(
                mark=marks.get(key, ""),
                axis=axis,
                ordinate_m=w.y1 if horizontal else w.x1,
                start_m=min(w.x1, w.x2) if horizontal else min(w.y1, w.y2),
                end_m=max(w.x1, w.x2) if horizontal else max(w.y1, w.y2),
                b_mm=float(d.get("b_mm", w.thickness * 1000)),
                D_mm=float(d.get("D_mm", 300.0)),
                span_m=float(d.get("span_m", w.length)),
                design=d.get("design", {}) or d,
            )
        )
    return runs


def build_structural_model(
    *,
    project_name: str,
    cfg: PlotConfig,
    layout: Layout,
    structural_design: dict,
    plinth_beams_data: dict | None = None,
) -> StructuralModel:
    """Assemble the drawable structural model for one approved+designed layout."""
    structapi = (structural_design or {}).get("structapi") or {}
    data = structapi.get("data") or {}

    grid = _grid_from_layout(layout)
    columns = _build_columns(grid, layout, data.get("columns") or {})
    footings = _build_footings(columns, data.get("footings") or {})
    beams_data = data.get("beams") or {}
    slabs_data = data.get("slabs") or {}

    gf_drawing = (
        build_floor_drawing(layout.ground_floor, cfg)
        if layout.ground_floor and layout.ground_floor.rooms
        else None
    )

    floors: list[FloorFraming] = []
    levels = [
        ("GF ROOF / FF FLOOR", "S-07", "S-08", layout.ground_floor, False),
        ("FF ROOF (TERRACE)", "S-09", "S-10", layout.first_floor, True),
    ]
    for label, drg_plan, drg_details, fp, terrace in levels:
        if fp is None:
            continue
        drawing = (
            gf_drawing
            if fp is layout.ground_floor
            else (build_floor_drawing(fp, cfg) if fp.rooms else None)
        )
        floors.append(
            FloorFraming(
                level_label=label,
                drg_plan=drg_plan,
                drg_details=drg_details,
                floor_plan=fp,
                drawing=drawing,
                beams=_build_beam_runs(grid, beams_data),
                slabs=_build_slab_panels(grid, slabs_data),
                is_terrace=terrace,
            )
        )

    inputs = data.get("inputs") or {}
    return StructuralModel(
        project_name=project_name,
        cfg=cfg,
        layout=layout,
        grid=grid,
        gf_drawing=gf_drawing,
        columns=columns,
        footings=footings,
        plinth_beams=_plinth_runs(
            gf_drawing.walls if gf_drawing else [], plinth_beams_data or {}
        ),
        floors=floors,
        materials={
            "fck": inputs.get("fck"),
            "fy": inputs.get("fy"),
            "exposure": inputs.get("exposure"),
            "sbc_kpa": inputs.get("sbc_kpa"),
            "storeys": inputs.get("storeys"),
            "storey_height_m": inputs.get("storey_height_m"),
            "seismic_zone": inputs.get("seismic_zone"),
        },
        lateral=data.get("lateral") or {},
        quantities=data.get("quantities") or {},
        assumptions=list(data.get("assumptions") or []),
        violations=list(data.get("violations") or []),
        disclaimer=structapi.get("disclaimer", ""),
        revision_id=(structural_design or {}).get("revision_id"),
        status=(structural_design or {}).get("status") or "",
        changelog=list((structural_design or {}).get("changelog") or []),
        structapi_data=data,
    )
