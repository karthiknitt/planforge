"""Shared foundation for the construction-grade Structural Drawing Set.

Every sheet in the set is built from the primitives here rather than from
bespoke per-sheet furniture, so the whole set registers, scales and reads as
one document.

Two frame kinds, deliberately different:

* :func:`plan_sheet_frame` — sheets that project model coordinates (column &
  footing plan, beam plans). It reproduces `pdf._draw_structural_floor`'s
  scale/origin arithmetic *exactly*, including ``reserve_w=SCHED_RESERVE``.
  That reserve is not decoration: omitting it (as the old
  ``_draw_sheet_frame`` did) yields a different scale denominator and a
  different ``ox`` than the sheets that do include it, so plan sheets of the
  same building failed to overlay. Sheets in a set must register.
* :func:`detail_sheet_frame` — sheets whose content is sections, schedules
  and pictorials with no model-space position. These get a plain bordered
  drawing area: no road strip, no plot boundary, no north arrow. Drawing plot
  furniture on a footing-section sheet is meaningless, and it was exactly
  that furniture which forced the defensive z-order clamping the old
  detail renderers carried.
"""

from __future__ import annotations

import string
from dataclasses import dataclass
from datetime import date

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.engine.models import PlotConfig
from app.engine.pdf import (
    MARGIN,
    ROAD_GAP,
    ROAD_H,
    TITLE_H,
    _centered_plot_oy,
    _draw_north_arrow,
    _draw_scale_bar,
    _standard_scale,
)
from app.engine.pdf import (
    SCHED_RESERVE as SCHED_RESERVE,
)
from app.engine.title_block import draw_title_block

#: Drawing register for the set. Ordered; the orchestrator emits them in this
#: order and every renderer takes its number from here rather than hardcoding
#: a string, so the register and the PDF can never disagree.
SHEET_REGISTER: tuple[tuple[str, str], ...] = (
    ("S-01", "GENERAL NOTES & SPECIFICATIONS"),
    ("S-02", "COLUMN & FOOTING PLAN"),
    ("S-03", "FOOTING DETAILS"),
    ("S-04", "COLUMN DETAILS & SCHEDULE"),
    ("S-05", "PLINTH BEAM PLAN"),
    ("S-06", "PLINTH BEAM DETAILS"),
    ("S-07", "GF ROOF / FF FLOOR BEAM & SLAB PLAN"),
    ("S-08", "GF ROOF BEAM DETAILS"),
    ("S-09", "FF ROOF BEAM & SLAB PLAN"),
    ("S-10", "FF ROOF BEAM DETAILS"),
    ("S-11", "SLAB REINFORCEMENT DETAILS"),
    ("S-12", "STAIRCASE DETAILS"),
)

SHEET_TITLES: dict[str, str] = dict(SHEET_REGISTER)

#: Standard detail scales, coarsest last. `detail_scale` picks the first that
#: fits, so a detail is drawn as large as the space honestly allows and the
#: printed "SCALE 1:N" is always a real ratio — unlike the hardcoded
#: points-per-mm constants these replace, which corresponded to no standard
#: scale at all (0.15 pt/mm ≈ 1:18.9).
DETAIL_DENOMS: tuple[int, ...] = (5, 10, 20, 25, 50, 75, 100, 200)

#: points per real-world millimetre at 1:1
_PT_PER_MM = 72.0 / 25.4

#: gap under a sheet's top border before content starts
HEADING_H = 22.0

_ROAD_SIDE_NAME = {"S": "SOUTH", "N": "NORTH", "E": "EAST", "W": "WEST"}


@dataclass(frozen=True)
class PlanFrame:
    """Model-space→paper-space projection for one plan sheet.

    ``(ox, oy, s, denom)`` are the same four values `_draw_structural_floor`
    returns, so a `PlanFrame` and that function's return value are directly
    comparable — which is what the cross-sheet registration test asserts.
    """

    ox: float
    oy: float
    s: float
    denom: int
    page_w: float
    page_h: float
    plot_px: float
    plot_py: float

    def px(self, x_m: float) -> float:
        return self.ox + x_m * self.s

    def py(self, y_m: float) -> float:
        return self.oy + y_m * self.s

    def as_tuple(self) -> tuple[float, float, float, int]:
        return self.ox, self.oy, self.s, self.denom


@dataclass(frozen=True)
class DetailFrame:
    """Plain rectangular drawing area for a non-plan sheet."""

    x0: float
    y0: float
    x1: float
    y1: float
    page_w: float
    page_h: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


def plan_sheet_frame(
    c: canvas.Canvas, cfg: PlotConfig, *, heading: str, drg_no: str
) -> PlanFrame:
    """Furniture + projection for a plan sheet: road strip, dashed plot
    boundary, north arrow, drawing-number stamp.

    The scale/origin arithmetic is copied from `_draw_structural_floor`
    verbatim (including ``reserve_w=SCHED_RESERVE``) so every plan sheet in
    the set — and the architectural PDF's own structural pages — share one
    projection.
    """
    page_w, page_h = A4
    s, denom = _standard_scale(cfg, page_w, page_h, reserve_w=SCHED_RESERVE)
    plot_px, plot_py = cfg.plot_width * s, cfg.plot_length * s
    ox = MARGIN + (page_w - 2 * MARGIN - SCHED_RESERVE - plot_px) / 2
    oy = _centered_plot_oy(
        page_h, plot_py, title_h=TITLE_H, margin=MARGIN, road_below=ROAD_H + ROAD_GAP
    )

    road_y = oy - ROAD_GAP - ROAD_H
    c.setFillColor(HexColor("#DDDDDD"))
    c.rect(ox, road_y, plot_px, ROAD_H, fill=1, stroke=0)
    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(ox + plot_px / 2, road_y + ROAD_H - 7, heading.upper())
    road_name = _ROAD_SIDE_NAME.get(cfg.road_side, "")
    c.setFillColor(HexColor("#444444"))
    c.setFont("Helvetica", 5.5)
    c.drawCentredString(
        ox + plot_px / 2, road_y + 3, f"ROAD  ({road_name})" if road_name else "ROAD"
    )

    c.setDash(5, 3)
    c.setStrokeColor(HexColor("#333333"))
    c.setLineWidth(0.5)
    c.rect(ox, oy, plot_px, plot_py, fill=0, stroke=1)
    c.setDash()

    _draw_north_arrow(c, page_w - MARGIN - 14, page_h - MARGIN - 16, 16)
    _drg_stamp(c, page_w, page_h, drg_no)

    return PlanFrame(ox, oy, s, denom, page_w, page_h, plot_px, plot_py)


def detail_sheet_frame(
    c: canvas.Canvas, *, heading: str, drg_no: str, continued: bool = False
) -> DetailFrame:
    """Plain bordered drawing area for a details/schedules sheet.

    No road strip, no plot boundary, no north arrow — none of which mean
    anything on a section sheet, and all of which previously forced clamping
    hacks to keep the real content from being painted over.
    """
    page_w, page_h = A4
    x0, x1 = MARGIN, page_w - MARGIN
    y1 = page_h - MARGIN
    y0 = TITLE_H + 12.0

    c.setStrokeColor(HexColor("#333333"))
    c.setLineWidth(0.7)
    c.rect(x0, y0, x1 - x0, y1 - y0, fill=0, stroke=1)

    label = f"{heading.upper()} (CONTD.)" if continued else heading.upper()
    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x0 + 6, y1 - 14, label)
    c.setLineWidth(0.5)
    c.line(x0, y1 - HEADING_H, x1, y1 - HEADING_H)

    _drg_stamp(c, page_w, page_h, drg_no)

    return DetailFrame(x0 + 8, y0 + 8, x1 - 8, y1 - HEADING_H - 8, page_w, page_h)


def _drg_stamp(c: canvas.Canvas, page_w: float, page_h: float, drg_no: str) -> None:
    """Right-aligned drawing-number stamp at the sheet's top-right corner.

    Right-aligned so it can never collide with the left-aligned notes block
    that plan sheets draw from the same top edge.
    """
    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica-Bold", 7)
    c.drawRightString(page_w - MARGIN, page_h - MARGIN + 4, f"DRG. NO. {drg_no}")


def structural_title_block(
    c: canvas.Canvas,
    *,
    project_name: str,
    cfg: PlotConfig,
    drg_no: str,
    sheet_title: str,
    page_w: float,
    scale_denom: int | None = None,
    scale_text: str | None = None,
    revision: str = "A",
    layout_label: str | None = None,
) -> None:
    """Title block for a structural sheet.

    Deliberately *not* `pdf._draw_title_block`: that helper is shaped for
    architectural pages and prints a "N BHK" CONFIG field, which structural
    callers could only satisfy by passing 0 and printing a meaningless
    "0 BHK". A structural sheet's identity is its drawing number, revision
    and scale — so those get cells instead.
    """
    fields: list[tuple[str, str]] = [
        ("PROJECT", project_name),
        ("DRG. NO.", drg_no),
        ("SHEET", sheet_title),
    ]
    if layout_label:
        fields.append(("LAYOUT", layout_label))
    fields.extend(
        [
            ("PLOT", f"{cfg.plot_width}x{cfg.plot_length} m"),
            ("SCALE", scale_text or (f"1:{scale_denom}" if scale_denom else "NTS")),
            ("REV", revision),
            ("DATE", date.today().strftime("%d %b %Y")),
        ]
    )
    draw_title_block(c, page_w, TITLE_H, fields)


# ── grid, bubbles, notes ─────────────────────────────────────────────────────


def draw_grid_and_bubbles(
    c: canvas.Canvas,
    frame: PlanFrame,
    v_xs: list[float],
    h_ys: list[float],
    bounds: tuple[float, float, float, float],
    *,
    ext: float = 10.0,
    bubble_r: float = 6.0,
) -> None:
    """Dashed centreline grid with lettered (X) / numbered (Y) bubbles at both
    ends of every line — lifted from `_draw_structural_floor` so plan sheets
    across the set carry an identical, cross-referenceable grid.
    """
    bx1, by1, bx2, by2 = bounds
    bx_lo, bx_hi = frame.px(bx1), frame.px(bx2)
    by_lo, by_hi = frame.py(by1), frame.py(by2)

    c.setStrokeColor(HexColor("#808080"))
    c.setLineWidth(0.4)
    c.setDash(4, 3)
    for x in v_xs:
        c.line(frame.px(x), by_lo - ext - 2, frame.px(x), by_hi + ext + 2)
    for y in h_ys:
        c.line(bx_lo - ext - 2, frame.py(y), bx_hi + ext + 2, frame.py(y))
    c.setDash()

    def bubble(px: float, py: float, lbl: str) -> None:
        c.setStrokeColor(HexColor("#555555"))
        c.setFillColor(HexColor("#FFFFFF"))
        c.setLineWidth(0.6)
        c.circle(px, py, bubble_r, fill=1, stroke=1)
        c.setFillColor(HexColor("#000000"))
        c.setFont("Helvetica-Bold", 6)
        c.drawCentredString(px, py - 2.2, lbl)

    for i, x in enumerate(v_xs):
        for yb in (by_lo - ext - bubble_r - 4, by_hi + ext + bubble_r + 4):
            bubble(frame.px(x), yb, grid_letter(i))
    for j, y in enumerate(h_ys):
        for xb in (bx_lo - ext - bubble_r - 4, bx_hi + ext + bubble_r + 4):
            bubble(xb, frame.py(y), str(j + 1))


def grid_letter(i: int) -> str:
    """Grid-line letter for X index ``i`` (A..Z, then AA, AB, ...)."""
    letters = string.ascii_uppercase
    if i < 26:
        return letters[i]
    return letters[i // 26 - 1] + letters[i % 26]


def draw_notes(
    c: canvas.Canvas,
    lines: list[str],
    x: float,
    y_top: float,
    *,
    leading: float = 9.0,
    title_size: float = 6.0,
    body_size: float = 5.5,
) -> float:
    """Left-aligned notes block; first line is the bold heading. Returns the
    y of the last line drawn."""
    y = y_top
    for i, line in enumerate(lines):
        c.setFont(
            "Helvetica-Bold" if i == 0 else "Helvetica",
            title_size if i == 0 else body_size,
        )
        c.setFillColor(HexColor("#000000"))
        c.drawString(x, y, line)
        y -= leading
    return y + leading


def draw_disclaimer(
    c: canvas.Canvas, text: str, x: float, y: float, *, max_chars: int = 150
) -> None:
    """structapi's disclaimer, echoed on every sheet of the set (required by
    the integration contract — the design is advisory until a licensed
    engineer signs it)."""
    if not text:
        return
    c.setFont("Helvetica-Oblique", 4.5)
    c.setFillColor(HexColor("#555555"))
    c.drawString(x, y, text[:max_chars])
    c.setFillColor(HexColor("#000000"))


def draw_plan_scale_bar(c: canvas.Canvas, frame: PlanFrame) -> None:
    _draw_scale_bar(c, MARGIN, TITLE_H + 2, frame.s, frame.denom)


# ── detail scaling ───────────────────────────────────────────────────────────


def detail_scale(
    extent_mm: float, avail_pt: float, *, denoms: tuple[int, ...] = DETAIL_DENOMS
) -> tuple[float, int]:
    """Largest standard detail scale at which ``extent_mm`` fits ``avail_pt``.

    Returns ``(points per real millimetre, denominator)``. Falls back to the
    coarsest listed denominator when nothing fits, so a caller always gets a
    usable scale and an honest printed ratio rather than silently drawing
    off-sheet.
    """
    if extent_mm <= 0 or avail_pt <= 0:
        return _PT_PER_MM / denoms[-1], denoms[-1]
    for denom in denoms:
        px_per_mm = _PT_PER_MM / denom
        if extent_mm * px_per_mm <= avail_pt:
            return px_per_mm, denom
    return _PT_PER_MM / denoms[-1], denoms[-1]


def fit_detail_scale(
    width_mm: float,
    height_mm: float,
    avail_w_pt: float,
    avail_h_pt: float,
    *,
    denoms: tuple[int, ...] = DETAIL_DENOMS,
) -> tuple[float, int]:
    """Two-axis form of :func:`detail_scale` — the detail must fit both ways."""
    for denom in denoms:
        px_per_mm = _PT_PER_MM / denom
        if width_mm * px_per_mm <= avail_w_pt and height_mm * px_per_mm <= avail_h_pt:
            return px_per_mm, denom
    return _PT_PER_MM / denoms[-1], denoms[-1]


def draw_scale_note(c: canvas.Canvas, x: float, y: float, denom: int) -> None:
    c.setFont("Helvetica-Bold", 5.5)
    c.setFillColor(HexColor("#000000"))
    c.drawString(x, y, f"SCALE 1:{denom}")


# ── pagination ───────────────────────────────────────────────────────────────


def paginate_boxes(
    items: list,
    height_of,
    *,
    top: float,
    bottom: float,
    gap: float = 15.0,
) -> list[list]:
    """Split ``items`` into pages by stacked height, dropping nothing.

    Pure function (no canvas) so page-breaking is unit-testable on its own.
    An item taller than a whole page still gets a page of its own rather than
    being skipped — the old renderers' ``break`` silently truncated the detail
    boxes whenever a plan produced more beam marks than fitted one sheet,
    which on a construction drawing means an unbuilt beam.
    """
    pages: list[list] = []
    current: list = []
    y = top
    for item in items:
        h = height_of(item)
        if current and y - h < bottom:
            pages.append(current)
            current = []
            y = top
        current.append(item)
        y -= h + gap
    if current:
        pages.append(current)
    return pages


# ── label de-collision ───────────────────────────────────────────────────────


class LabelPlacer:
    """Proximity de-collision for annotation text.

    Generalised from the ad-hoc two-candidate check in
    `_draw_structural_floor`'s column tags. Callers offer candidate anchor
    points in preference order; the first that clears every already-placed
    label wins. If every candidate collides the first is used anyway and
    reported as unresolved — on a construction drawing a slightly crowded tag
    beats a missing one, but the caller can still count how often it happened.
    """

    def __init__(self, dx: float = 16.0, dy: float = 7.0) -> None:
        self.dx = dx
        self.dy = dy
        self.placed: list[tuple[float, float]] = []
        self.collisions = 0

    def _free(self, x: float, y: float) -> bool:
        return not any(
            abs(x - px) < self.dx and abs(y - py) < self.dy for px, py in self.placed
        )

    def place(self, candidates: list[tuple[float, float]]) -> tuple[float, float]:
        if not candidates:
            raise ValueError("LabelPlacer.place requires at least one candidate")
        for x, y in candidates:
            if self._free(x, y):
                self.placed.append((x, y))
                return x, y
        self.collisions += 1
        self.placed.append(candidates[0])
        return candidates[0]
