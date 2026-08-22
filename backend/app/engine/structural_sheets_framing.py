"""Framing half of the Structural Drawing Set: S-05 … S-10.

Four sheets, three renderers, one detail primitive:

* **S-05 / S-06** — plinth beam plan and details.
* **S-07 / S-09** — beam & slab plan, one per framing level.
* **S-08 / S-10** — beam details, one per framing level.

Two structural decisions shape the module:

1. **One parameterised beam-detail renderer.** The renderer this replaces
   carried four near-identical ~70-line copies of the same cross-section
   pictorial, differing only in mark prefix and sheet title. Every beam detail
   in the set now comes out of :func:`_draw_beam_detail`, so a detailing
   improvement lands on all four sheets at once instead of three of them
   drifting.

2. **Per-level sheets differ by underlay and annotation, not by renderer.**
   structapi designs one framing for the whole building (see
   ``structural_data``), so :func:`render_framing_plan` and
   :func:`render_framing_details` take a :class:`FloorFraming` and read their
   drawing number, heading and geometry underlay from it. That is how both
   floors get covered from one code path.

Nothing is ever dropped for want of space: detail boxes and schedule rows are
paginated onto ``(CONTD.)`` pages. A silently truncated member list on a
construction drawing is an unbuilt beam.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from reportlab.lib.colors import HexColor, white
from reportlab.pdfgen import canvas

from app.engine.pdf import (
    MARGIN,
    ROAD_GAP,
    ROAD_H,
    SCHED_BAND_H,
    SCHED_PAD,
    SCHED_ROW_H,
    TITLE_H,
    _cluster,
    _draw_dim_chains,
    _draw_generic_schedule_table,
    _generic_schedule_height,
    _pdf_draw_double_line_wall,
    _schedule_column_x,
)
from app.engine.section_render import hatch_polygon
from app.engine.structural_data import (
    BeamRun,
    FloorFraming,
    SlabPanel,
    Stirrup,
    StructuralModel,
)
from app.engine.structural_sheet import (
    SHEET_TITLES,
    LabelPlacer,
    PlanFrame,
    detail_sheet_frame,
    draw_disclaimer,
    draw_grid_and_bubbles,
    draw_notes,
    draw_plan_scale_bar,
    draw_scale_note,
    fit_detail_scale,
    paginate_boxes,
    plan_sheet_frame,
    structural_title_block,
)

_BEAM_C = HexColor("#000000")
_COL_C = HexColor("#000000")
_SLAB_C = HexColor("#0066CC")
_STEEL_C = HexColor("#AA0000")
_ROOM_C = HexColor("#CCCCCC")
_DIM_C = HexColor("#333333")

#: vertical budget inside one beam-detail box (points)
_HEAD_H = 16.0
_SEC_MAX_H = 92.0
_ELEV_MAX_H = 78.0
_ROW_GAP = 10.0
_BOX_PAD = 6.0
_BOX_GAP = 14.0

#: IS 13920 / ordinary detailing practice: stirrups are closed up over a
#: length of 2D from each support face, where shear is highest.
_END_ZONE_D_FACTOR = 2.0

#: nominal support width drawn under a beam elevation (mm) when no column
#: size is to hand — a drawn support that is honestly nominal beats a beam
#: floating in space with no bearing shown.
_NOMINAL_SUPPORT_MM = 300.0

#: vertical space `plan_sheet_frame`'s north arrow needs at the top-right,
#: withheld from the schedule column on plan sheets
_NORTH_ARROW_CLEAR = 40.0


# ── design-dict reading (defensive) ──────────────────────────────────────────


@dataclass(frozen=True)
class _BeamSteel:
    """Reinforcement read off one beam's design dict.

    Every field has a drawable fallback; ``assumed`` names the fields that
    fell back, so callouts can say so instead of presenting a default as a
    designed value.
    """

    n_bot: int
    dia_bot: float
    n_top: int
    dia_top: float
    doubly: bool
    sv: float
    dia_st: float
    legs: int
    cover: float
    assumed: tuple[str, ...] = ()

    @property
    def caveat(self) -> str:
        return "  (ASSUMED: " + ", ".join(self.assumed) + ")" if self.assumed else ""


def _num(value: object, default: float) -> tuple[float, bool]:
    try:
        if value is None:
            return default, False
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default, False
    return (out, True) if out > 0 else (default, False)


def _inner_design(design: dict) -> dict:
    """Beam records reach here in two shapes.

    Roof beams keep structapi's element dict (``{b_mm, span_m, design: {...}}``)
    while plinth beams are already unwrapped by ``_plinth_runs``. Resolve both
    rather than making the caller know which one it holds.
    """
    inner = design.get("design")
    return inner if isinstance(inner, dict) else design


def _read_steel(source: BeamRun | dict) -> _BeamSteel:
    """Typed-first (Task 31): when handed a BeamRun, its parsed
    BarGroup/Stirrup/Cover beats the design-dict read; the dict path below is
    the migration fallback, unchanged (unit tests still pin it). The
    `assumed` flags fire exactly when neither the typed entity nor the
    payload supplied the value."""
    if isinstance(source, BeamRun):
        run: BeamRun | None = source
        design = source.design or {}
    else:
        run = None
        design = source or {}
    bottom_bars = run.bottom_bars if run else None
    top_bars = run.top_bars if run else None
    stirrups = run.stirrups if run else None
    cover_t = run.cover if run else None
    d = _inner_design(design)
    st = d.get("stirrups") if isinstance(d.get("stirrups"), dict) else {}
    inputs = design.get("inputs") if isinstance(design.get("inputs"), dict) else {}
    assumed: list[str] = []

    doubly = bool(d.get("doubly_reinforced"))

    if bottom_bars is not None:
        n_bot_f, dia_bot = float(bottom_bars.quantity), bottom_bars.diameter_mm
    else:
        n_bot_f, ok = _num(d.get("n_bars"), 2.0)
        if not ok:
            assumed.append("BOT NOS")
        dia_bot, ok = _num(d.get("bar_dia"), 12.0)
        if not ok:
            assumed.append("BAR DIA")
    if top_bars is not None:
        n_top_f, dia_top = float(top_bars.quantity), top_bars.diameter_mm
    else:
        n_top_f, ok = _num(d.get("n_bars_comp"), 2.0)
        if doubly and not ok:
            assumed.append("TOP NOS")
        dia_top, _ = _num(d.get("bar_dia_comp"), dia_bot)
    if stirrups is not None:
        sv, dia_st = stirrups.spacing_mm, stirrups.diameter_mm
        legs_f = float(stirrups.legs) if stirrups.legs is not None else 2.0
    else:
        sv, ok = _num(st.get("sv_provided"), 150.0)
        if not ok:
            assumed.append("STIRRUP SPACING")
        dia_st, ok = _num(st.get("dia") or inputs.get("stirrup_dia"), 8.0)
        if not ok:
            assumed.append("STIRRUP DIA")
        legs_f, _ = _num(st.get("legs"), 2.0)
    if cover_t is not None:
        cover = cover_t.mm
    else:
        cover, _ = _num(d.get("cover_mm") or inputs.get("cover_mm"), 25.0)

    return _BeamSteel(
        n_bot=max(1, int(round(n_bot_f))),
        dia_bot=dia_bot,
        n_top=max(2, int(round(n_top_f))),
        dia_top=dia_top,
        doubly=doubly,
        sv=sv,
        dia_st=dia_st,
        legs=max(2, int(round(legs_f))),
        cover=cover,
        assumed=tuple(assumed),
    )


def _bot_callout(st: _BeamSteel) -> str:
    return f"{st.n_bot} NOS {st.dia_bot:.0f}ø BOT"


def _top_callout(st: _BeamSteel) -> str:
    txt = f"{st.n_top} NOS {st.dia_top:.0f}ø TOP"
    return txt if st.doubly else txt + " (NOM. HANGER)"


def _stirrup_callout(st: _BeamSteel) -> str:
    return f"{st.dia_st:.0f}ø {st.legs}-LEGGED STIRRUPS @ {st.sv:.0f} c/c"


def _end_zone_spacing(st: _BeamSteel) -> float:
    """Closer end-zone spacing: half the design spacing, rounded down to a
    25 mm module and never finer than 75 mm (site-buildable)."""
    return max(75.0, (st.sv / 2.0) // 25.0 * 25.0)


# ── schedules ────────────────────────────────────────────────────────────────
#
# Two header/width sets per schedule. The plan sheets place their schedule in
# the reserved right-hand column, which is exactly ``SCHED_W`` (148 pt) wide —
# the full descriptive headers do not fit there at the table's 5 pt type, so
# the narrow set abbreviates them and the columns sum to exactly 148. The
# details sheets have the whole frame width and use the full headers.

_BEAM_HDRS_WIDE = (
    "MARK",
    "SIZE (b x D mm)",
    "SPAN (m)",
    "TOP STEEL",
    "BOTTOM STEEL",
    "STIRRUPS",
    "NOS",
)
_BEAM_COLS_WIDE = (34.0, 80.0, 46.0, 66.0, 74.0, 88.0, 26.0)
_BEAM_HDRS_NARROW = ("MARK", "SIZE mm", "SPAN m", "TOP", "BOT", "STIRR", "NOS")
_BEAM_COLS_NARROW = (18.0, 28.0, 22.0, 22.0, 22.0, 24.0, 12.0)

_SLAB_HDRS_WIDE = (
    "MARK",
    "SIZE (lx x ly m)",
    "TYPE",
    "THK (mm)",
    "MAIN STEEL (c/c)",
    "DIST. STEEL (c/c)",
)
_SLAB_COLS_WIDE = (34.0, 84.0, 60.0, 52.0, 92.0, 92.0)
_SLAB_HDRS_NARROW = ("MARK", "SIZE m", "TYPE", "THK", "MAIN", "DIST")
_SLAB_COLS_NARROW = (18.0, 30.0, 30.0, 15.0, 27.5, 27.5)


def _mark_key(mark: str) -> tuple[str, int]:
    m = re.match(r"([A-Za-z]*)(\d*)", mark)
    if not m:
        return mark, 0
    return m.group(1), int(m.group(2) or 0)


def _distinct_marks(beams: list[BeamRun]) -> list[tuple[str, BeamRun, int]]:
    """``(mark, representative run, count)`` per designed mark, in mark order.

    Runs with an empty mark are wall lines with no design entry — they are
    drawn on the plan but carry no schedule row, because inventing a mark for
    them would put a member in the schedule that was never designed.
    """
    grouped: dict[str, list[BeamRun]] = {}
    for b in beams:
        if b.mark:
            grouped.setdefault(b.mark, []).append(b)
    return [
        (mark, grouped[mark][0], len(grouped[mark]))
        for mark in sorted(grouped, key=_mark_key)
    ]


def _beam_schedule_rows(beams: list[BeamRun]) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    for mark, run, nos in _distinct_marks(beams):
        st = _read_steel(run)
        rows.append(
            (
                mark,
                f"{run.b_mm:.0f}x{run.D_mm:.0f}",
                f"{_beam_span(run):.2f}",
                f"{st.n_top}-{st.dia_top:.0f}ø",
                f"{st.n_bot}-{st.dia_bot:.0f}ø",
                f"{st.dia_st:.0f}ø@{st.sv:.0f}",
                str(nos),
            )
        )
    return rows


def _beam_span(run: BeamRun) -> float:
    """Designed span, falling back to the run's own drawn length when the
    design carries none — a beam detail with no span cannot show curtailment."""
    return run.span_m if run.span_m > 0 else abs(run.end_m - run.start_m)


def _compact(text: str) -> str:
    """``"10 φ @ 150 c/c"`` -> ``"10φ@150"``.

    The trailing ``c/c`` is dropped, not lost: it moves into the schedule's
    column header, which buys the ~8 pt needed for the value to stay inside
    its cell in the plan sheets' 148 pt reserved column.
    """
    return re.sub(r"c/c$", "", re.sub(r"\s+", "", str(text))) or "—"


def _stirrup_bar_string(s: Stirrup | None) -> str | None:
    """Render a typed Stirrup in structapi's bar-string shape, so the
    _compact() pipeline prints byte-identical text."""
    if s is None:
        return None
    return f"{s.diameter_mm:g} φ @ {s.spacing_mm:g} c/c"


def _bar_text(typed: Stirrup | None, raw: dict | None) -> str:
    """Typed-first (Task 31): the parsed Stirrup's canonical bar string beats
    the raw payload; when absent, the raw ``{"bar": "…"}`` passes through
    verbatim (including unparseable junk — a migration fallback, not a
    validator)."""
    canonical = _stirrup_bar_string(typed)
    if canonical is not None:
        return canonical
    return (raw or {}).get("bar") or "—"


def _slab_steel_text(panel: SlabPanel) -> tuple[str, str]:
    """``(main, distribution)`` bar strings from structapi's slab record.

    One-way panels carry ``main``/``distribution``; two-way panels carry a
    ``strips`` dict keyed by span direction — both directions are main steel
    there, so the short-span bottom strip is reported in the MAIN column and
    the long-span bottom strip in the other.
    """
    d = panel.design or {}
    if not panel.is_two_way:
        main = _bar_text(panel.main_steel, d.get("main"))
        dist = _bar_text(panel.dist_steel, d.get("distribution"))
        return _compact(main), _compact(dist)
    strips = d.get("strips") or {}
    short_raw = next(
        (v for k, v in strips.items() if "short" in k and "bot" in k), None
    )
    long_raw = next((v for k, v in strips.items() if "long" in k and "bot" in k), None)
    short = _bar_text(panel.main_steel, short_raw)
    long_ = _bar_text(panel.dist_steel, long_raw)
    return _compact(short), _compact(long_)


def _slab_schedule_rows(slabs: list[SlabPanel]) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    for p in slabs:
        main, dist = _slab_steel_text(p)
        lx = p.lx_m if p.lx_m > 0 else abs(p.x2 - p.x1)
        ly = p.ly_m if p.ly_m > 0 else abs(p.y2 - p.y1)
        rows.append(
            (
                p.mark,
                f"{lx:.2f}x{ly:.2f}",
                p.kind.upper(),
                f"{p.D_mm:.0f}",
                main,
                dist,
            )
        )
    return rows


@dataclass(frozen=True)
class _Sched:
    title: str
    headers: tuple[str, ...]
    col_ws: tuple[float, ...]
    rows: list[tuple[str, ...]]

    @property
    def height(self) -> float:
        return _generic_schedule_height(len(self.rows))


def _paginate_schedules(
    specs: list[_Sched], avail_h: float, gap: float = SCHED_PAD
) -> list[list[_Sched]]:
    """Stack schedules down a fixed-width column, splitting rows across pages.

    A table too tall for the remaining space continues on the next page under
    a ``(CONTD.)`` title rather than losing its tail rows.
    """
    pages: list[list[_Sched]] = []
    cur: list[_Sched] = []
    y = avail_h
    for spec in specs:
        if not spec.rows:
            continue
        idx, part = 0, 0
        while idx < len(spec.rows):
            cap = int((y - SCHED_BAND_H) // SCHED_ROW_H) - 1
            if cap < 1:
                if cur:
                    pages.append(cur)
                    cur, y = [], avail_h
                    continue
                cap = 1  # page too short for even one row: draw it anyway
            take = spec.rows[idx : idx + cap]
            cur.append(
                _Sched(
                    spec.title if part == 0 else f"{spec.title} (CONTD.)",
                    spec.headers,
                    spec.col_ws,
                    take,
                )
            )
            y -= _generic_schedule_height(len(take)) + gap
            idx += len(take)
            part += 1
    if cur:
        pages.append(cur)
    return pages


def _draw_schedule_stack(
    c: canvas.Canvas, specs: list[_Sched], x: float, y_top: float
) -> None:
    y = y_top
    for spec in specs:
        _draw_generic_schedule_table(
            c, spec.title, spec.headers, spec.col_ws, spec.rows, x, y
        )
        y -= spec.height + SCHED_PAD


# ── plan-sheet primitives ────────────────────────────────────────────────────


def _grid_lines(model: StructuralModel, drawing) -> tuple[list[float], list[float]]:
    """Designed grid when structapi had one, else wall centrelines.

    The fallback matters: the grid is what the bubbles and slab bays are set
    out from, so a sheet with no grid is a sheet no one can dimension off.
    """
    if model.grid.ok:
        return list(model.grid.x_lines_m), list(model.grid.y_lines_m)
    if drawing is None:
        return [], []
    return (
        _cluster([w.x1 for w in drawing.walls if abs(w.x1 - w.x2) < 1e-9]),
        _cluster([w.y1 for w in drawing.walls if abs(w.y1 - w.y2) < 1e-9]),
    )


def _draw_beams(c: canvas.Canvas, frame: PlanFrame, beams: list[BeamRun]) -> None:
    """Every beam at its true width, double-line.

    A single 1.5 pt stroke (what this replaces) conveys no width at all: a
    230 mm and a 300 mm beam drew identically and neither could be scaled off
    the sheet.
    """
    c.setStrokeColor(_BEAM_C)
    for b in beams:
        x1, y1, x2, y2 = b.endpoints
        thickness = max(1.2, b.b_mm / 1000.0 * frame.s)
        _pdf_draw_double_line_wall(
            c,
            frame.px(x1),
            frame.py(y1),
            frame.px(x2),
            frame.py(y2),
            thickness,
            [],
            0.7,
        )


def _draw_beam_marks(
    c: canvas.Canvas, frame: PlanFrame, beams: list[BeamRun], placer: LabelPlacer
) -> None:
    c.setFont("Helvetica-Bold", 5.0)
    c.setFillColor(_BEAM_C)
    for b in beams:
        if not b.mark:
            continue  # undesigned wall line — drawn, deliberately unlabelled
        x1, y1, x2, y2 = b.endpoints
        mx, my = frame.px((x1 + x2) / 2), frame.py((y1 + y2) / 2)
        qx, qy = frame.px(x1 + (x2 - x1) * 0.25), frame.py(y1 + (y2 - y1) * 0.25)
        off = 4.0 if b.axis == "x" else 0.0
        cands = [
            (mx + off, my + 3.0),
            (mx + off, my - 7.0),
            (qx + off, qy + 3.0),
            (qx + off, qy - 7.0),
        ]
        lx, ly = placer.place(cands)
        c.drawCentredString(lx, ly, b.mark)


def _draw_columns(c: canvas.Canvas, frame: PlanFrame, model: StructuralModel) -> None:
    c.setFillColor(_COL_C)
    for col in model.columns:
        w = max(3.0, col.b_mm / 1000.0 * frame.s)
        h = max(3.0, col.D_mm / 1000.0 * frame.s)
        c.rect(
            frame.px(col.cx) - w / 2, frame.py(col.cy) - h / 2, w, h, fill=1, stroke=0
        )


def _plan_furniture(
    c: canvas.Canvas, frame: PlanFrame, model: StructuralModel, drawing
) -> None:
    """Grid, chain dimensions, scale bar and disclaimer for a plan sheet.

    The bottom chain lane is pushed up to just under the road strip rather
    than left at ``_draw_dim_chains``' default (which sits in the bottom page
    margin): on these sheets the plot is centred well above that lane, so the
    default leaves the bottom chain floating detached from the building it
    measures. The disclaimer sits right of centre because the scale bar owns
    the bottom-left corner.
    """
    v_xs, h_ys = _grid_lines(model, drawing)
    if drawing is not None:
        if v_xs and h_ys:
            draw_grid_and_bubbles(c, frame, v_xs, h_ys, drawing.bounds)
        _draw_dim_chains(
            c,
            drawing,
            frame.s,
            frame.ox,
            frame.oy,
            frame.plot_px,
            frame.plot_py,
            bottom_lane_y=frame.oy - ROAD_GAP - ROAD_H - 10.0,
        )
    draw_plan_scale_bar(c, frame)
    draw_disclaimer(c, model.disclaimer, frame.page_w / 2 - 40.0, TITLE_H + 2)


def _draw_room_underlay(c: canvas.Canvas, frame: PlanFrame, floor_plan) -> None:
    c.setStrokeColor(_ROOM_C)
    c.setLineWidth(0.4)
    for room in floor_plan.rooms:
        c.rect(
            frame.px(room.x),
            frame.py(room.y),
            room.width * frame.s,
            room.depth * frame.s,
            fill=0,
            stroke=1,
        )


def _double_arrow(
    c: canvas.Canvas, x1: float, y1: float, x2: float, y2: float, head: float = 2.5
) -> None:
    c.line(x1, y1, x2, y2)
    if abs(x2 - x1) >= abs(y2 - y1):
        sgn = 1.0 if x2 > x1 else -1.0
        for tip, s in ((x1, sgn), (x2, -sgn)):
            c.line(tip, y1, tip + s * head, y1 + head * 0.7)
            c.line(tip, y1, tip + s * head, y1 - head * 0.7)
    else:
        sgn = 1.0 if y2 > y1 else -1.0
        for tip, s in ((y1, sgn), (y2, -sgn)):
            c.line(x1, tip, x1 + head * 0.7, tip + s * head)
            c.line(x1, tip, x1 - head * 0.7, tip + s * head)


def _draw_slab_panels(
    c: canvas.Canvas, frame: PlanFrame, slabs: list[SlabPanel]
) -> None:
    """Bay rectangles with mark, thickness, span type and steel directions.

    Direction is taken from the drawn bay, not from the design's ``lx``/``ly``:
    the arrows have to point along the geometry actually on the sheet. A
    one-way panel carries main steel across its SHORT span with distribution
    steel perpendicular; a two-way panel carries main steel both ways.
    """
    for p in slabs:
        px1, py1 = frame.px(p.x1), frame.py(p.y1)
        px2, py2 = frame.px(p.x2), frame.py(p.y2)
        w, h = px2 - px1, py2 - py1
        if w < 6 or h < 6:
            continue
        inset = min(4.0, w * 0.08, h * 0.08)
        c.setStrokeColor(_SLAB_C)
        c.setLineWidth(0.4)
        c.setDash(2, 2)
        c.rect(px1 + inset, py1 + inset, w - 2 * inset, h - 2 * inset, fill=0, stroke=1)
        c.setDash()

        cx, cy = px1 + w / 2, py1 + h / 2
        c.setFillColor(_SLAB_C)
        c.setFont("Helvetica-Bold", 5.5)
        c.drawCentredString(cx, cy + 3.0, p.mark)
        c.setFont("Helvetica", 4.2)
        c.drawCentredString(cx, cy - 3.0, f"{p.D_mm:.0f} THK")
        c.drawCentredString(cx, cy - 8.5, p.kind.upper())

        # short bay axis carries the one-way main steel
        short_is_x = (p.x2 - p.x1) <= (p.y2 - p.y1)
        ax_in = min(10.0, w * 0.2), min(10.0, h * 0.2)
        c.setStrokeColor(_SLAB_C)
        c.setLineWidth(0.4)
        c.setFont("Helvetica", 3.6)
        x_lbl = "MAIN" if (p.is_two_way or short_is_x) else "DIST."
        y_lbl = "MAIN" if (p.is_two_way or not short_is_x) else "DIST."
        ay = py1 + h * 0.24
        _double_arrow(c, px1 + ax_in[0], ay, px2 - ax_in[0], ay)
        c.drawCentredString(cx, ay + 1.6, x_lbl)
        ax = px1 + w * 0.26
        _double_arrow(c, ax, py1 + ax_in[1], ax, py2 - ax_in[1])
        c.saveState()
        # off-centre: the panel's mark/thickness/type block owns the centre
        c.translate(ax - 1.6, py1 + h * 0.74)
        c.rotate(90)
        c.drawCentredString(0, 0, y_lbl)
        c.restoreState()


# ── the unified beam-detail renderer ─────────────────────────────────────────


@dataclass(frozen=True)
class _BoxMetrics:
    sec_px: float
    sec_denom: int
    bw: float
    bh: float
    sec_box_w: float
    elev_px: float
    elev_denom: int
    ew: float
    eh: float
    sup_h: float
    row1_h: float
    row2_h: float
    total_h: float


def _box_metrics(
    b_mm: float, D_mm: float, span_m: float, avail_w: float
) -> _BoxMetrics:
    """Single source of truth for a detail box's geometry.

    Both the pagination height function and the drawing code read it, so a
    box can never be laid out at one height and drawn at another.
    """
    sec_box_w = min(160.0, max(96.0, avail_w * 0.34))
    sec_px, sec_denom = fit_detail_scale(
        max(b_mm, 1.0), max(D_mm, 1.0), sec_box_w - 44.0, _SEC_MAX_H - 30.0
    )
    bw, bh = b_mm * sec_px, D_mm * sec_px
    row1_h = max(bh + 46.0, 52.0)

    span_mm = max(span_m, 0.3) * 1000.0
    elev_px, elev_denom = fit_detail_scale(
        span_mm, max(D_mm, 1.0), avail_w - 44.0, _ELEV_MAX_H - 30.0
    )
    ew, eh = span_mm * elev_px, D_mm * elev_px
    sup_h = max(6.0, eh * 0.55)
    row2_h = 12.0 + eh + sup_h + 22.0

    return _BoxMetrics(
        sec_px=sec_px,
        sec_denom=sec_denom,
        bw=bw,
        bh=bh,
        sec_box_w=sec_box_w,
        elev_px=elev_px,
        elev_denom=elev_denom,
        ew=ew,
        eh=eh,
        sup_h=sup_h,
        row1_h=row1_h,
        row2_h=row2_h,
        total_h=_HEAD_H + row1_h + _ROW_GAP + row2_h + _BOX_PAD,
    )


def _bar_xs(x0: float, width: float, n: int, edge: float) -> list[float]:
    if n <= 1:
        return [x0 + width / 2]
    span = max(width - 2 * edge, 1.0)
    return [x0 + edge + span * i / (n - 1) for i in range(n)]


def _dim_h(
    c: canvas.Canvas, x1: float, x2: float, y: float, text: str, tick: float = 2.0
) -> None:
    c.setStrokeColor(_DIM_C)
    c.setLineWidth(0.35)
    c.line(x1, y, x2, y)
    for p in (x1, x2):
        c.line(p, y - tick, p, y + tick)
        c.line(p - 1.4, y - 1.4, p + 1.4, y + 1.4)
    c.setFillColor(_DIM_C)
    c.setFont("Helvetica", 4.6)
    c.drawCentredString((x1 + x2) / 2, y - 5.5, text)


def _dim_v(c: canvas.Canvas, x: float, y1: float, y2: float, text: str) -> None:
    c.setStrokeColor(_DIM_C)
    c.setLineWidth(0.35)
    c.line(x, y1, x, y2)
    for p in (y1, y2):
        c.line(x - 2.0, p, x + 2.0, p)
        c.line(x - 1.4, p - 1.4, x + 1.4, p + 1.4)
    c.setFillColor(_DIM_C)
    c.setFont("Helvetica", 4.6)
    c.saveState()
    c.translate(x - 2.0, (y1 + y2) / 2)
    c.rotate(90)
    c.drawCentredString(0, 0, text)
    c.restoreState()


def _draw_beam_section(
    c: canvas.Canvas,
    x: float,
    top: float,
    b_mm: float,
    D_mm: float,
    st: _BeamSteel,
    m: _BoxMetrics,
) -> None:
    """Dimensioned b x D cross-section with the stirrup drawn as a real closed
    rectangle (plus hooks) and every bar at its scaled diameter."""
    sx = x + 26.0
    sy = top - 14.0 - m.bh

    c.setFillColor(white)
    c.setStrokeColor(_BEAM_C)
    c.setLineWidth(0.8)
    c.rect(sx, sy, m.bw, m.bh, fill=1, stroke=1)

    cov = max(1.2, st.cover * m.sec_px)
    st_dia = max(0.4, st.dia_st * m.sec_px)
    # the stirrup itself, not a text note about one
    c.setStrokeColor(_STEEL_C)
    c.setLineWidth(max(0.4, st_dia))
    sw, sh = m.bw - 2 * cov, m.bh - 2 * cov
    if sw > 1.5 and sh > 1.5:
        c.rect(sx + cov, sy + cov, sw, sh, fill=0, stroke=1)
        # both 135° hook legs turned into the core, at the standard 10d length
        hook = min(max(1.6, 10.0 * st_dia) * 0.7071, sw * 0.45, sh * 0.45)
        hx, hy = sx + cov, sy + m.bh - cov
        c.setLineWidth(max(0.35, st_dia * 0.8))
        c.line(hx, hy, hx + hook, hy - hook)
        c.line(hx + hook * 0.6, hy, hx + hook * 1.6, hy - hook)

    r_bot = max(0.7, st.dia_bot / 2.0 * m.sec_px)
    r_top = max(0.7, st.dia_top / 2.0 * m.sec_px)
    c.setFillColor(_STEEL_C)
    for bx in _bar_xs(sx, m.bw, st.n_bot, cov + st_dia + r_bot):
        c.circle(bx, sy + cov + st_dia + r_bot, r_bot, fill=1, stroke=0)
    for bx in _bar_xs(sx, m.bw, st.n_top, cov + st_dia + r_top):
        c.circle(bx, sy + m.bh - cov - st_dia - r_top, r_top, fill=1, stroke=0)

    _dim_h(c, sx, sx + m.bw, sy - 9.0, f"{b_mm:.0f}")
    _dim_v(c, sx - 11.0, sy, sy + m.bh, f"{D_mm:.0f}")
    draw_scale_note(c, sx, sy - 20.0, m.sec_denom)
    c.setFont("Helvetica-Bold", 5.0)
    c.setFillColor(_BEAM_C)
    c.drawString(sx, top - 7.0, "SECTION")


def _stirrup_run(
    c: canvas.Canvas, x0: float, x1: float, y0: float, y1: float, pitch: float
) -> bool:
    """Draw stirrup lines from ``x0`` to ``x1``. Returns True when the true
    pitch was too fine to draw and a legible pitch was substituted."""
    coarse = pitch < 1.5
    step = max(pitch, 1.5)
    px = x0
    guard = 0
    while px <= x1 and guard < 400:
        c.line(px, y0, px, y1)
        px += step
        guard += 1
    return coarse


def _draw_beam_elevation(
    c: canvas.Canvas,
    x: float,
    top: float,
    D_mm: float,
    span_m: float,
    st: _BeamSteel,
    m: _BoxMetrics,
    avail_w: float,
) -> None:
    """Longitudinal elevation: supports, bar runs with anchorage and support
    curtailment, and the stirrup zoning (closer over 2D from each support)."""
    ex = x + 22.0
    ey = top - 12.0 - m.eh
    sup_w = max(4.0, _NOMINAL_SUPPORT_MM * m.elev_px)

    for cx in (ex, ex + m.ew):
        pts = [
            (cx - sup_w / 2, ey - m.sup_h),
            (cx + sup_w / 2, ey - m.sup_h),
            (cx + sup_w / 2, ey),
            (cx - sup_w / 2, ey),
        ]
        hatch_polygon(c, pts, "rcc", spacing_pt=3.0)
        c.setStrokeColor(_BEAM_C)
        c.setLineWidth(0.6)
        c.rect(cx - sup_w / 2, ey - m.sup_h, sup_w, m.sup_h, fill=0, stroke=1)

    c.setFillColor(white)
    c.setStrokeColor(_BEAM_C)
    c.setLineWidth(0.8)
    c.rect(ex, ey, m.ew, m.eh, fill=1, stroke=1)

    cov = max(1.0, st.cover * m.elev_px)
    y_bot, y_top = ey + cov, ey + m.eh - cov
    hook = min(max(2.5, m.eh * 0.4), max(2.5, m.eh - 2 * cov))

    c.setStrokeColor(_STEEL_C)
    c.setLineWidth(0.7)
    # bottom bars run through into both supports and turn up (anchorage)
    ax0, ax1 = ex - sup_w / 2 + 1.0, ex + m.ew + sup_w / 2 - 1.0
    c.line(ax0, y_bot, ax1, y_bot)
    c.line(ax0, y_bot, ax0, y_bot + hook)
    c.line(ax1, y_bot, ax1, y_bot + hook)
    # top bars continuous over the supports, with extra bars curtailed at L/4
    c.line(ax0, y_top, ax1, y_top)
    c.line(ax0, y_top, ax0, y_top - hook)
    c.line(ax1, y_top, ax1, y_top - hook)
    c.setDash(2, 1.5)
    c.setLineWidth(0.5)
    y_extra = y_top - max(0.8, (y_top - y_bot) * 0.16)
    c.line(ex, y_extra, ex + m.ew * 0.25, y_extra)
    c.line(ex + m.ew * 0.75, y_extra, ex + m.ew, y_extra)
    c.setDash()

    sv_end = _end_zone_spacing(st)
    zone_mm = min(_END_ZONE_D_FACTOR * max(D_mm, 1.0), span_m * 1000.0 / 3.0)
    zone_pt = zone_mm * m.elev_px
    c.setStrokeColor(_STEEL_C)
    c.setLineWidth(0.35)
    coarse = _stirrup_run(c, ex + 1.0, ex + zone_pt, y_bot, y_top, sv_end * m.elev_px)
    coarse |= _stirrup_run(
        c, ex + zone_pt, ex + m.ew - zone_pt, y_bot, y_top, st.sv * m.elev_px
    )
    coarse |= _stirrup_run(
        c, ex + m.ew - zone_pt, ex + m.ew - 1.0, y_bot, y_top, sv_end * m.elev_px
    )

    c.setFillColor(_BEAM_C)
    c.setFont("Helvetica", 4.2)
    lbl_y = ey + m.eh + 3.0
    c.drawCentredString(ex + zone_pt / 2, lbl_y, f"@{sv_end:.0f}")
    c.drawCentredString(ex + m.ew / 2, lbl_y, f"@{st.sv:.0f} c/c")
    c.drawCentredString(ex + m.ew - zone_pt / 2, lbl_y, f"@{sv_end:.0f}")

    dim_y = ey - m.sup_h - 9.0
    _dim_h(c, ex, ex + m.ew, dim_y, f"SPAN {span_m:.2f} M")
    c.setFont("Helvetica-Bold", 5.0)
    c.setFillColor(_BEAM_C)
    c.drawString(ex, top - 4.0, "LONGITUDINAL ELEVATION")
    draw_scale_note(c, x + avail_w - 46.0, dim_y - 5.5, m.elev_denom)
    if coarse:
        c.setFont("Helvetica-Oblique", 3.8)
        c.setFillColor(HexColor("#555555"))
        c.drawString(ex, dim_y - 11.0, "STIRRUP PITCH SHOWN INDICATIVE AT THIS SCALE")


def _draw_beam_detail(
    c: canvas.Canvas,
    mark: str,
    b_mm: float,
    D_mm: float,
    span_m: float,
    design: dict | BeamRun,
    x: float,
    y: float,
    avail_w: float,
    avail_h: float,
) -> float:
    """One complete beam detail — cross-section + longitudinal elevation.

    The single renderer behind S-06, S-08 and S-10. ``y`` is the top of the
    box; the return value is the height consumed, matching
    :func:`_box_metrics` exactly so pagination and drawing agree.

    ``avail_h`` is advisory: a box is never silently dropped for being taller
    than the space offered — the pagination layer gives an oversized box its
    own page instead.
    """
    m = _box_metrics(b_mm, D_mm, span_m, avail_w)
    # during the Task 31 migration this is called with either the BeamRun
    # (typed-first read) or its raw design dict (legacy read) — identical
    # steel when the payload keyed it the old way
    st = _read_steel(design)

    c.setFillColor(_BEAM_C)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x, y - 9.0, f"{mark}  —  {b_mm:.0f} x {D_mm:.0f} MM  —  BEAM DETAIL")
    c.setStrokeColor(HexColor("#999999"))
    c.setLineWidth(0.3)
    c.line(x, y - 12.0, x + avail_w, y - 12.0)

    row1_top = y - _HEAD_H
    _draw_beam_section(c, x, row1_top, b_mm, D_mm, st, m)

    cal_x = x + m.sec_box_w + 6.0
    c.setFillColor(_BEAM_C)
    c.setFont("Helvetica", 5.2)
    for i, line in enumerate(
        (_bot_callout(st), _top_callout(st), _stirrup_callout(st))
    ):
        c.drawString(cal_x, row1_top - 6.0 - i * 8.0, line)
    c.setFont("Helvetica", 4.6)
    c.drawString(
        cal_x,
        row1_top - 30.0,
        f"CLEAR COVER {st.cover:.0f} MM  •  END ZONE 2D "
        f"@ {_end_zone_spacing(st):.0f} c/c",
    )
    if st.assumed:
        c.setFont("Helvetica-Oblique", 4.4)
        c.setFillColor(HexColor("#8A4B00"))
        c.drawString(cal_x, row1_top - 38.0, f"NOT IN DESIGN DATA{st.caveat}")
        c.setFillColor(_BEAM_C)

    _draw_beam_elevation(
        c, x, row1_top - m.row1_h - _ROW_GAP, D_mm, max(span_m, 0.3), st, m, avail_w
    )
    return m.total_h


# ── page items ───────────────────────────────────────────────────────────────


@dataclass
class _Item:
    """A paginatable block on a details sheet: its height and how to draw it."""

    height: float
    draw: Callable[[canvas.Canvas, float, float, float], None]
    tag: str = ""


def _beam_items(beams: list[BeamRun], avail_w: float) -> list[_Item]:
    items: list[_Item] = []
    for mark, run, _nos in _distinct_marks(beams):
        span = _beam_span(run)
        m = _box_metrics(run.b_mm, run.D_mm, span, avail_w)

        # every loop-varying value is bound as a default: a late-bound closure
        # here would draw the last mark's detail under every other mark's title
        def _draw(
            c: canvas.Canvas,
            x: float,
            y: float,
            w: float,
            mark: str = mark,
            run: BeamRun = run,
            span: float = span,
            box_h: float = m.total_h,
        ) -> None:
            _draw_beam_detail(c, mark, run.b_mm, run.D_mm, span, run, x, y, w, box_h)

        items.append(_Item(m.total_h, _draw, mark))
    return items


def _notes_item(lines: list[str]) -> _Item:
    def _draw(c: canvas.Canvas, x: float, y: float, w: float) -> None:
        draw_notes(c, lines, x, y - 6.0)

    return _Item(9.0 * len(lines) + 8.0, _draw, "notes")


def _schedule_items(specs: list[_Sched], page_h: float) -> list[_Item]:
    """Schedules as paginatable items, split so no chunk exceeds a page."""
    max_rows = max(1, int((page_h - SCHED_BAND_H) // SCHED_ROW_H) - 1)
    items: list[_Item] = []
    for spec in specs:
        if not spec.rows:
            continue
        for part, i in enumerate(range(0, len(spec.rows), max_rows)):
            chunk = _Sched(
                spec.title if part == 0 else f"{spec.title} (CONTD.)",
                spec.headers,
                spec.col_ws,
                spec.rows[i : i + max_rows],
            )

            def _draw(
                c: canvas.Canvas,
                x: float,
                y: float,
                w: float,
                chunk: _Sched = chunk,
            ) -> None:
                _draw_generic_schedule_table(
                    c, chunk.title, chunk.headers, chunk.col_ws, chunk.rows, x, y
                )

            items.append(_Item(chunk.height, _draw, chunk.title))
    return items


# ── S-05: PLINTH BEAM PLAN ───────────────────────────────────────────────────


def render_plinth_beam_plan(c: canvas.Canvas, model: StructuralModel) -> int:
    frame = plan_sheet_frame(c, model.cfg, heading=SHEET_TITLES["S-05"], drg_no="S-05")
    drawing = model.gf_drawing
    gf = model.layout.ground_floor if model.layout else None

    if gf is not None:
        _draw_room_underlay(c, frame, gf)

    _draw_beams(c, frame, model.plinth_beams)
    _draw_columns(c, frame, model)
    _draw_beam_marks(c, frame, model.plinth_beams, LabelPlacer())

    _plan_furniture(c, frame, model, drawing)

    specs = [
        _Sched(
            "PLINTH BEAM SCHEDULE",
            _BEAM_HDRS_NARROW,
            _BEAM_COLS_NARROW,
            _beam_schedule_rows(model.plinth_beams),
        )
    ]
    return _render_plan_schedules(c, model, specs, frame, "S-05", SHEET_TITLES["S-05"])


def _render_plan_schedules(
    c: canvas.Canvas,
    model: StructuralModel,
    specs: list[_Sched],
    frame: PlanFrame,
    drg_no: str,
    heading: str,
    *,
    defer_schedules: bool = False,
    notes: list[str] | None = None,
) -> int:
    """Draw schedules in the plan sheet's reserved column; overflow continues
    on ``(CONTD.)`` pages rather than losing rows.

    With ``defer_schedules``, nothing is drawn on the plan sheet at all — the
    notes and every schedule go onto their own continuation sheet. The
    framing plans need this: once the plot is drawn at 1:100 it reaches the
    full page width, so a schedule stacked in the top-right corner lands on
    the plan's own dimension chains and grid bubbles. A drawing you cannot
    read the dimensions off is worse than an extra sheet.

    Draws the plan page's own title block too — it has to land before the
    first ``showPage()``, so it cannot be left to the caller to add after
    this returns.
    """
    sched_x = _schedule_column_x(frame.page_w, MARGIN)
    # clear of the north arrow `plan_sheet_frame` stamps into the same
    # top-right corner — the table's opaque white fill would otherwise erase
    # all but the outermost edge of it
    col_top = frame.page_h - MARGIN - _NORTH_ARROW_CLEAR
    avail_h = col_top - (TITLE_H + SCHED_PAD)
    pages = [] if defer_schedules else _paginate_schedules(specs, avail_h)

    if pages:
        _draw_schedule_stack(c, pages[0], sched_x, col_top)
    structural_title_block(
        c,
        project_name=model.project_name,
        cfg=model.cfg,
        drg_no=drg_no,
        sheet_title=heading,
        page_w=frame.page_w,
        scale_denom=frame.denom,
        layout_label=model.layout_label,
    )
    if defer_schedules:
        return 1 + _render_deferred_schedule_sheet(
            c, model, specs, drg_no, heading, notes
        )
    if not pages:
        return 1

    for extra in pages[1:]:
        c.showPage()
        dframe = detail_sheet_frame(c, heading=heading, drg_no=drg_no, continued=True)
        _draw_schedule_stack(c, extra, dframe.x0, dframe.y1)
        draw_disclaimer(c, model.disclaimer, dframe.x0, TITLE_H + 2)
        structural_title_block(
            c,
            project_name=model.project_name,
            cfg=model.cfg,
            drg_no=drg_no,
            sheet_title=heading,
            page_w=dframe.page_w,
            scale_text="NTS",
            layout_label=model.layout_label,
        )
    return len(pages)


def _render_deferred_schedule_sheet(
    c: canvas.Canvas,
    model: StructuralModel,
    specs: list[_Sched],
    drg_no: str,
    heading: str,
    notes: list[str] | None,
) -> int:
    """Notes + schedules on their own sheet(s), continuing the plan's number.

    Notes are laid out as just another paginatable block alongside the
    schedules, so neither can be pushed off the sheet by the other.
    """
    c.showPage()
    frame = detail_sheet_frame(c, heading=heading, drg_no=drg_no, continued=True)

    items: list[_Item] = []
    if notes:
        items.append(_notes_item(notes))
    items += _schedule_items(specs, frame.height)

    pages = paginate_boxes(
        items, lambda it: it.height, top=frame.y1, bottom=frame.y0, gap=_BOX_GAP
    ) or [[]]

    for i, page_items in enumerate(pages):
        if i:
            c.showPage()
            frame = detail_sheet_frame(
                c, heading=heading, drg_no=drg_no, continued=True
            )
        y = frame.y1
        for item in page_items:
            item.draw(c, frame.x0, y, frame.width)
            y -= item.height + _BOX_GAP
        draw_disclaimer(c, model.disclaimer, frame.x0, TITLE_H + 2)
        structural_title_block(
            c,
            project_name=model.project_name,
            cfg=model.cfg,
            drg_no=drg_no,
            sheet_title=heading,
            page_w=frame.page_w,
            scale_text="NTS",
            layout_label=model.layout_label,
        )
    return len(pages)


# ── S-06 / S-08 / S-10: beam details ─────────────────────────────────────────


def _render_beam_details_sheet(
    c: canvas.Canvas,
    model: StructuralModel,
    beams: list[BeamRun],
    *,
    drg_no: str,
    heading: str,
    sched_title: str,
    notes: list[str],
) -> int:
    """Shared body of S-06, S-08 and S-10.

    Every distinct mark gets a full detail; the schedule is laid out as just
    another paginatable block, so it can never be pushed off the sheet by the
    details or vice versa.
    """
    frame = detail_sheet_frame(c, heading=heading, drg_no=drg_no)
    avail_w = frame.width
    page_h = frame.height

    specs = [
        _Sched(
            sched_title, _BEAM_HDRS_WIDE, _BEAM_COLS_WIDE, _beam_schedule_rows(beams)
        )
    ]
    # notes ride the same pagination as the details: laid out as a block they
    # can never be overprinted by a detail box that grew taller than expected
    items = (
        _schedule_items(specs, page_h)
        + _beam_items(beams, avail_w)
        + [_notes_item(notes)]
    )

    pages = paginate_boxes(
        items, lambda it: it.height, top=frame.y1, bottom=frame.y0, gap=_BOX_GAP
    )

    for i, page_items in enumerate(pages):
        if i:
            c.showPage()
            frame = detail_sheet_frame(
                c, heading=heading, drg_no=drg_no, continued=True
            )
        y = frame.y1
        for item in page_items:
            item.draw(c, frame.x0, y, avail_w)
            y -= item.height + _BOX_GAP
        draw_disclaimer(c, model.disclaimer, frame.x0, TITLE_H + 2)
        structural_title_block(
            c,
            project_name=model.project_name,
            cfg=model.cfg,
            drg_no=drg_no,
            sheet_title=heading,
            page_w=frame.page_w,
            scale_text="AS SHOWN",
            layout_label=model.layout_label,
        )
    return len(pages)


def render_plinth_beam_details(c: canvas.Canvas, model: StructuralModel) -> int:
    # S-05's plan notes are merged in here rather than printed on the plan
    # itself: at 1:100 the plan fills the sheet, and this sheet is mostly
    # text already, so the two note blocks belong together on one page.
    marked = len([b for b in model.plinth_beams if b.mark])
    return _render_beam_details_sheet(
        c,
        model,
        model.plinth_beams,
        drg_no="S-06",
        heading=SHEET_TITLES["S-06"],
        sched_title="PLINTH BEAM SCHEDULE",
        notes=[
            "PLINTH BEAM NOTES (PLAN ON DRG. S-05):",
            f"1. {marked} DESIGNED PLINTH BEAM RUNS — SEE SCHEDULE THIS SHEET",
            "2. BEAMS DRAWN TO TRUE WIDTH; SOFFIT AT PLINTH LEVEL",
            "3. UNMARKED LINES ON S-05 CARRY NO DESIGN ENTRY — REFER ENGINEER",
            "",
            "PLINTH BEAM DETAILING NOTES:",
            "4. STIRRUPS CLOSED AT 2D FROM EACH SUPPORT FACE",
            "5. BOTTOM BARS ANCHORED INTO SUPPORTS WITH STANDARD HOOK",
            "6. LAPS STAGGERED; NOT MORE THAN 50% AT ONE SECTION",
        ],
    )


def render_framing_details(
    c: canvas.Canvas, model: StructuralModel, framing: FloorFraming
) -> int:
    heading = f"{framing.level_label} BEAM DETAILS"
    return _render_beam_details_sheet(
        c,
        model,
        framing.beams,
        drg_no=framing.drg_details,
        heading=heading,
        sched_title=f"{framing.level_label} BEAM SCHEDULE",
        notes=[
            "BEAM DETAILING NOTES:",
            "1. STIRRUPS CLOSED AT 2D FROM EACH SUPPORT FACE",
            "2. EXTRA TOP BARS OVER SUPPORTS CURTAILED AT L/4",
            "3. BOTTOM BARS ANCHORED INTO SUPPORTS WITH STANDARD HOOK",
            "4. LAPS STAGGERED; NOT MORE THAN 50% AT ONE SECTION",
        ],
    )


# ── S-07 / S-09: beam & slab plan ────────────────────────────────────────────


def render_framing_plan(
    c: canvas.Canvas, model: StructuralModel, framing: FloorFraming
) -> int:
    """One renderer, both framing levels.

    The underlay is ``framing.drawing`` — the floor *below* this framing level,
    which is the correct convention: a beam plan is read against the rooms it
    spans over.
    """
    heading = f"{framing.level_label} BEAM & SLAB PLAN"
    frame = plan_sheet_frame(c, model.cfg, heading=heading, drg_no=framing.drg_plan)
    drawing = framing.drawing

    _draw_room_underlay(c, frame, framing.floor_plan)
    _draw_slab_panels(c, frame, framing.slabs)
    _draw_beams(c, frame, framing.beams)
    _draw_columns(c, frame, model)
    _draw_beam_marks(c, frame, framing.beams, LabelPlacer())

    _plan_furniture(c, frame, model, drawing)

    notes = [
        f"{framing.level_label} FRAMING NOTES:",
        f"1. {len(framing.slabs)} SLAB PANELS BOUNDED BY BEAMS — SEE SLAB SCHEDULE",
        "2. MAIN STEEL DIRECTION ARROWED ON EACH PANEL",
        "3. BEAMS DRAWN TO TRUE WIDTH; SOFFIT AT BEAM DEPTH BELOW SLAB",
        f"4. REINFORCEMENT DETAILS ON DRG. {framing.drg_details}",
    ]
    if framing.is_terrace:
        notes.append(
            "5. TERRACE: WATERPROOFING OVER SLAB WITH 1:100 SLOPE TO RAINWATER OUTLETS"
        )
    specs = [
        _Sched(
            "SLAB SCHEDULE",
            _SLAB_HDRS_NARROW,
            _SLAB_COLS_NARROW,
            _slab_schedule_rows(framing.slabs),
        ),
        _Sched(
            "BEAM SCHEDULE",
            _BEAM_HDRS_NARROW,
            _BEAM_COLS_NARROW,
            _beam_schedule_rows(framing.beams),
        ),
    ]
    # Notes and schedules both go to a continuation sheet: at 1:100 the plan
    # occupies the full page width, so anything stacked over it lands on the
    # dimension chains and grid bubbles.
    return _render_plan_schedules(
        c,
        model,
        specs,
        frame,
        framing.drg_plan,
        heading,
        defer_schedules=True,
        notes=notes,
    )


__all__ = [
    "render_framing_details",
    "render_framing_plan",
    "render_plinth_beam_details",
    "render_plinth_beam_plan",
]
