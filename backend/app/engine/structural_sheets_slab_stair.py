"""Sheets S-11 (Slab Reinforcement Details) and S-12 (Staircase Details).

Both sheets are pure details/schedules — no plot-space projection — so they
are built on `structural_sheet.detail_sheet_frame` like S-01. Steel callouts
read structapi's designed spacing/diameter defensively: the exact key names
in a live payload are not pinned anywhere in this codebase, so `_find_numeric`
searches the design dict by key-substring rather than a hardcoded key, and
falls back to a clearly-labelled IS 456 minimum-steel value when nothing
designed is found. A fabricated number is never presented as a designed one.
"""

from __future__ import annotations

import math
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.engine.pdf import MARGIN, _draw_generic_schedule_table
from app.engine.section_render import hatch_polygon
from app.engine.structural_data import SlabPanel, StructuralModel
from app.engine.structural_sheet import (
    SHEET_TITLES,
    DetailFrame,
    draw_disclaimer,
    draw_scale_note,
    fit_detail_scale,
    paginate_boxes,
    structural_title_block,
)

#: bar area (mm²) for standard IS 1786 diameters, used only to size a nominal
#: (minimum-steel) callout when structapi's design dict carries no spacing.
_BAR_AREA_MM2 = {6: 28.3, 8: 50.3, 10: 78.5, 12: 113.1, 16: 201.1}

#: typical Indian residential riser/tread ranges (mm) — used only to flag a
#: derived value as unusual on the sheet, never to reject it.
_RISER_OK_MM = (150.0, 190.0)
_TREAD_OK_MM = (250.0, 300.0)

_PANEL_BOX_H = 250.0
_STAIR_SECTION_COVER_MM = 20.0


# ── shared steel lookup ──────────────────────────────────────────────────────


def _find_numeric(d: Any, substrings: tuple[str, ...], _depth: int = 0) -> float | None:
    """Depth-limited search for a numeric value whose key contains every
    substring in ``substrings`` (case-insensitive). structapi's exact key
    naming for slab/stair steel is undocumented in this codebase, so this
    searches by meaning rather than by a hardcoded key."""
    if _depth > 3 or not isinstance(d, dict):
        return None
    for k, v in d.items():
        kl = str(k).lower()
        if all(s in kl for s in substrings) and isinstance(v, (int, float)):
            return float(v)
    for v in d.values():
        if isinstance(v, dict):
            found = _find_numeric(v, substrings, _depth + 1)
            if found is not None:
                return found
    return None


def _nominal_steel(D_mm: float, fy: float | None) -> tuple[int, int]:
    """IS 456 cl 26.5.2.1 minimum slab steel: 0.12% of gross area for HYSD
    (fy >= 415), 0.15% for mild steel. Returns (dia_mm, spacing_mm) using an
    8mm bar, spacing rounded down to the nearest 25mm and clamped to a
    buildable 75-300mm range."""
    pct = 0.0012 if (fy or 500) >= 415 else 0.0015
    ast_per_m = pct * 1000.0 * max(D_mm, 1.0)  # mm^2 per metre width
    dia = 8
    spacing = (_BAR_AREA_MM2[dia] * 1000.0) / ast_per_m
    spacing = 25.0 * math.floor(spacing / 25.0)
    spacing = max(75.0, min(300.0, spacing))
    return dia, int(spacing)


_TYPED_STEEL_ATTR = {"main": "main_steel", "dist": "dist_steel", "top": "top_steel"}


def _steel_pair(
    panel_or_design: SlabPanel | dict,
    tag: tuple[str, ...],
    D_mm: float,
    fy: float | None,
) -> tuple[int, int, bool]:
    """Return (dia_mm, spacing_mm, is_nominal) for a steel group identified
    by ``tag`` (e.g. ``("main",)``, ``("dist",)``, ``("top",)``).

    Typed-first (Task 31): a panel's parsed Stirrup beats the fuzzy-key
    design-dict read; the dict path stays as the migration fallback."""
    typed = None
    design = panel_or_design
    if isinstance(panel_or_design, SlabPanel):
        design = panel_or_design.design or {}
        attr = _TYPED_STEEL_ATTR.get(tag[0]) if tag else None
        typed = getattr(panel_or_design, attr, None) if attr else None
    if typed is not None and typed.diameter_mm > 0 and typed.spacing_mm > 0:
        return int(round(typed.diameter_mm)), int(round(typed.spacing_mm)), False
    dia = _find_numeric(design, (*tag, "dia"))
    spacing = _find_numeric(design, (*tag, "spac"))
    if dia is not None and spacing is not None:
        return int(round(dia)), int(round(spacing)), False
    n_dia, n_spacing = _nominal_steel(D_mm, fy)
    return n_dia, n_spacing, True


def _callout(dia: int, spacing: int, direction: str, nominal: bool) -> str:
    base = f"{dia}ø @ {spacing} c/c {direction}"
    return f"{base} (NOMINAL - MIN STEEL)" if nominal else base


# ── S-11 SLAB REINFORCEMENT DETAILS ─────────────────────────────────────────


def _slab_types(model: StructuralModel) -> list[SlabPanel]:
    """Distinct designed panel types across all floors, deduped by the
    tuple that actually determines the detail (span pair, kind, case,
    thickness) — the same design repeated across bays needs one detail."""
    seen: dict[tuple, SlabPanel] = {}
    for floor in model.floors:
        for panel in floor.slabs:
            key = (panel.lx_m, panel.ly_m, panel.kind, panel.case, panel.D_mm)
            seen.setdefault(key, panel)
    return list(seen.values())


def render_slab_reinforcement_details(c: canvas.Canvas, model: StructuralModel) -> int:
    page_w, page_h = A4
    panels = _slab_types(model)

    if not panels:
        frame = _frame(c, "S-11")
        c.setFont("Helvetica", 8)
        c.drawString(frame.x0 + 6, frame.y1 - 24, "NO DESIGNED SLAB PANELS FOUND.")
        _finish_page(c, model, page_w, "S-11")
        return 1

    frame0 = _frame(c, "S-11")
    avail_h = frame0.height - 60  # reserve room for the schedule on page 1
    pages = paginate_boxes(
        panels, height_of=lambda _p: _PANEL_BOX_H, top=avail_h, bottom=0.0, gap=14
    )

    fy = (model.materials or {}).get("fy")
    page_count = 0
    for page_idx, page_panels in enumerate(pages):
        frame = frame0 if page_idx == 0 else _frame(c, "S-11", continued=True)
        y = frame.y1
        if page_idx == 0:
            y = _draw_slab_schedule(c, panels, frame.x0, y, fy) - 14

        for panel in page_panels:
            y = _draw_panel_detail(c, panel, frame.x0, y, frame.width, fy) - 14

        _finish_page(c, model, page_w, "S-11")
        page_count += 1
        if page_idx < len(pages) - 1:
            c.showPage()

    return page_count


def _draw_slab_schedule(
    c: canvas.Canvas, panels: list[SlabPanel], x: float, y_top: float, fy: float | None
) -> float:
    headers = (
        "MARK",
        "SIZE (LXxLY)",
        "TYPE",
        "THK",
        "MAIN STEEL",
        "DIST STEEL",
        "TOP @ SUPPORT",
    )
    col_ws = (32.0, 62.0, 42.0, 30.0, 92.0, 92.0, 92.0)
    rows = []
    for p in panels:
        main_dia, main_sp, main_nom = _steel_pair(p, ("main",), p.D_mm, fy)
        dist_dia, dist_sp, dist_nom = _steel_pair(p, ("dist",), p.D_mm, fy)
        top_dia, top_sp, top_nom = _steel_pair(p, ("top",), p.D_mm, fy)
        rows.append(
            (
                p.mark,
                f"{p.lx_m:.2f}x{p.ly_m:.2f}",
                p.kind.upper(),
                f"{p.D_mm:.0f}",
                _callout(main_dia, main_sp, "", main_nom),
                _callout(dist_dia, dist_sp, "", dist_nom),
                _callout(top_dia, top_sp, "", top_nom),
            )
        )
    height = _draw_generic_schedule_table(
        c, "SLAB SCHEDULE", headers, col_ws, rows, x, y_top
    )
    return y_top - height


def _draw_panel_detail(
    c: canvas.Canvas,
    panel: SlabPanel,
    x: float,
    y_top: float,
    avail_w: float,
    fy: float | None,
) -> float:
    """One panel type: bar-layout plan + edge/corner steel + section, with
    callouts. Returns the y below the box drawn."""
    box_h = _PANEL_BOX_H
    y_bot = y_top - box_h

    c.setFont("Helvetica-Bold", 7)
    c.setFillColor(HexColor("#000000"))
    c.drawString(
        x,
        y_top - 9,
        f"PANEL {panel.mark} — {panel.kind.upper()} SLAB, CASE {panel.case or '-'}",
    )

    plan_w = avail_w * 0.55
    plan_h = box_h - 34
    px0, py0 = x, y_bot + 20
    px_s, denom = fit_detail_scale(
        panel.lx_m * 1000, panel.ly_m * 1000, plan_w - 10, plan_h
    )
    pw = panel.lx_m * 1000 * px_s
    ph = panel.ly_m * 1000 * px_s

    main_dia, main_sp, main_nom = _steel_pair(panel, ("main",), panel.D_mm, fy)
    dist_dia, dist_sp, dist_nom = _steel_pair(panel, ("dist",), panel.D_mm, fy)
    top_dia, top_sp, top_nom = _steel_pair(panel, ("top",), panel.D_mm, fy)

    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.8)
    c.rect(px0, py0, pw, ph, fill=0, stroke=1)

    # Main steel: one-way runs only along the short span (assumed x here per
    # structapi's lx<=ly convention); two-way runs both, short-span layer
    # drawn first/lower per the callout note below.
    _draw_bar_family(c, px0, py0, pw, ph, main_sp * px_s, vertical=True, dash=False)
    if panel.is_two_way:
        _draw_bar_family(c, px0, py0, pw, ph, dist_sp * px_s, vertical=False, dash=True)
    else:
        _draw_bar_family(c, px0, py0, pw, ph, dist_sp * px_s, vertical=False, dash=True)

    # discontinuous-edge top steel: hatch band inset 0.15L-0.25L from each edge
    edge_in = min(pw, ph) * 0.20
    c.setFillColor(HexColor("#00000022"))
    hatch_polygon(
        c,
        [
            (px0, py0 + ph),
            (px0 + pw, py0 + ph),
            (px0 + pw, py0 + ph - edge_in),
            (px0, py0 + ph - edge_in),
        ],
        "rcc",
        spacing_pt=3.0,
    )
    if panel.is_two_way:
        corner = min(pw, ph) * 0.15
        hatch_polygon(
            c,
            [(px0, py0 + ph), (px0 + corner, py0 + ph), (px0, py0 + ph - corner)],
            "rcc",
            spacing_pt=2.5,
        )

    c.setFont("Helvetica", 4.5)
    c.setFillColor(HexColor("#000000"))
    c.drawString(
        px0,
        py0 + ph + 8,
        f"TOP STEEL AT SUPPORT (0.15L-0.25L): {_callout(top_dia, top_sp, '', top_nom)}",
    )
    if panel.is_two_way:
        c.drawString(
            px0, py0 - 8, "CORNER: TORSION MESH TOP+BOTTOM BOTH FACES, IS 456 cl D-1.8"
        )
    draw_scale_note(c, px0, py0 - 16 if panel.is_two_way else py0 - 8, denom)

    # section, to the right of the plan
    sx0 = x + plan_w + 12
    sec_w = avail_w - plan_w - 12
    _draw_panel_section(c, panel, sx0, y_bot + 20, sec_w, plan_h, top_dia, top_nom, fy)

    lines = [
        f"MAIN: {_callout(main_dia, main_sp, 'ALONG SHORT SPAN (BOTTOM)', main_nom)}",
        f"DIST: {_callout(dist_dia, dist_sp, 'ALONG LONG SPAN (TOP OF MAIN)' if not panel.is_two_way else 'LONG SPAN (LOWER LAYER OVER MAIN — CHECK LAYERING ORDER)', dist_nom)}",
    ]
    ly = py0 + ph + 20
    c.setFont("Helvetica", 5)
    for line in lines:
        c.drawString(sx0, ly, line)
        ly -= 7

    return y_bot


def _draw_bar_family(
    c: canvas.Canvas,
    x0: float,
    y0: float,
    w: float,
    h: float,
    spacing_pt: float,
    *,
    vertical: bool,
    dash: bool,
) -> None:
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.4)
    if dash:
        c.setDash(2, 2)
    spacing_pt = max(spacing_pt, 3.0)
    if vertical:
        n = max(1, int(w / spacing_pt))
        t = x0 + spacing_pt / 2
        for _ in range(min(n, 20)):
            if t >= x0 + w:
                break
            c.line(t, y0, t, y0 + h)
            t += spacing_pt
    else:
        n = max(1, int(h / spacing_pt))
        t = y0 + spacing_pt / 2
        for _ in range(min(n, 20)):
            if t >= y0 + h:
                break
            c.line(x0, t, x0 + w, t)
            t += spacing_pt
    c.setDash()


def _draw_panel_section(
    c: canvas.Canvas,
    panel: SlabPanel,
    x0: float,
    y0: float,
    w: float,
    h: float,
    top_dia: int,
    top_nominal: bool,
    fy: float | None,
) -> None:
    sec_w = min(w, 120.0)
    D_pt, _ = fit_detail_scale(panel.D_mm, panel.D_mm, sec_w, 40.0)
    slab_h = max(panel.D_mm * D_pt, 8.0)
    sy = y0 + h / 2 - slab_h / 2
    hatch_polygon(
        c,
        [(x0, sy), (x0 + sec_w, sy), (x0 + sec_w, sy + slab_h), (x0, sy + slab_h)],
        "rcc",
        spacing_pt=3.0,
    )
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.6)
    c.rect(x0, sy, sec_w, slab_h, fill=0, stroke=1)

    cover_pt = _STAIR_SECTION_COVER_MM * D_pt
    c.setFillColor(HexColor("#000000"))
    for cx in (x0 + 10, x0 + sec_w / 2, x0 + sec_w - 10):
        c.circle(cx, sy + cover_pt, 1.3, fill=1, stroke=0)  # bottom steel
        if top_dia:
            c.circle(cx, sy + slab_h - cover_pt, 1.0, fill=1, stroke=0)  # top steel

    # cover dimension + chair symbol
    c.setFont("Helvetica", 4.5)
    c.drawString(
        x0, sy - 8, f"D = {panel.D_mm:.0f}mm, COVER = {_STAIR_SECTION_COVER_MM:.0f}mm"
    )
    c.setLineWidth(0.3)
    c.line(
        x0 + sec_w / 2 - 6, sy + cover_pt, x0 + sec_w / 2 - 6, sy + slab_h - cover_pt
    )
    c.drawString(x0 + sec_w / 2 - 4, sy + slab_h / 2, "CHAIR")
    c.setFont("Helvetica-Bold", 5)
    c.drawString(x0, sy - 16, "SECTION")


# ── S-12 STAIRCASE DETAILS ──────────────────────────────────────────────────


def _staircase_room(model: StructuralModel):
    for floor in model.floors:
        if floor.floor_plan is None:
            continue
        for room in floor.floor_plan.rooms:
            if room.type == "staircase" and floor.drawing and floor.drawing.stair:
                return floor, room
    return None, None


def render_staircase_details(c: canvas.Canvas, model: StructuralModel) -> int:
    page_w, page_h = A4
    frame = _frame(c, "S-12")
    floor, room = _staircase_room(model)

    if floor is None or room is None:
        c.setFont("Helvetica", 8)
        c.drawString(
            frame.x0 + 6, frame.y1 - 24, "NO STAIRCASE ROOM FOUND IN THIS LAYOUT."
        )
        _finish_page(c, model, page_w, "S-12")
        return 1

    stair = floor.drawing.stair
    materials = model.materials or {}
    storey_h_m = materials.get("storey_height_m") or 3.0
    fy = materials.get("fy")

    tread_count = max(stair.tread_count, 1)
    riser_count = tread_count + 1  # a flight of N treads rises N+1 risers
    run_len_m = room.depth if room.depth >= room.width else room.width
    riser_mm = (storey_h_m * 1000.0) / riser_count
    going_mm = (run_len_m * 1000.0) / tread_count
    waist_span_m = math.hypot(run_len_m, storey_h_m / 2)
    waist_mm = max(120.0, (waist_span_m * 1000.0) / 20.0)
    landing_w_m = min(1.0, min(room.width, room.depth) * 0.4) or 1.0

    warn = []
    if not (_RISER_OK_MM[0] <= riser_mm <= _RISER_OK_MM[1]):
        warn.append(
            f"RISER {riser_mm:.0f}mm OUTSIDE TYPICAL RESIDENTIAL RANGE 150-190mm"
        )
    if not (_TREAD_OK_MM[0] <= going_mm <= _TREAD_OK_MM[1]):
        warn.append(
            f"GOING {going_mm:.0f}mm OUTSIDE TYPICAL RESIDENTIAL RANGE 250-300mm"
        )

    # steel: search across whichever design dict carries a staircase entry
    stair_design = _stair_design_dict(model)
    main_dia, main_sp, main_nom = _steel_pair(stair_design, ("main",), waist_mm, fy)
    dist_dia, dist_sp, dist_nom = _steel_pair(stair_design, ("dist",), waist_mm, fy)

    y = frame.y1
    c.setFont("Helvetica-Bold", 7)
    c.drawString(
        frame.x0,
        y - 9,
        f"STAIRCASE — ROOM {room.id.upper()} ({room.width:.2f}m x {room.depth:.2f}m)",
    )
    y -= 20

    sec_h = 190.0
    sx0, sy0 = frame.x0, y - sec_h
    sec_w = frame.width * 0.58
    section_bottom = _draw_stair_section(
        c,
        sx0,
        sy0,
        sec_w,
        sec_h,
        tread_count,
        riser_count,
        riser_mm,
        going_mm,
        waist_mm,
        landing_w_m,
        main_dia,
        main_sp,
        main_nom,
        dist_dia,
        dist_sp,
        dist_nom,
    )

    px0 = sx0 + sec_w + 14
    plan_w = frame.width - sec_w - 14
    _draw_stair_plan(c, px0, sy0, plan_w, sec_h, room, stair, landing_w_m)

    y = min(sy0 - 14, section_bottom)
    c.setFont("Helvetica", 5.5)
    landing_beam = f"{max(230, round(waist_mm / 10) * 10):.0f}x{round(storey_h_m * 100):.0f}mm (BEARING >= 200mm ON WALL)"
    c.drawString(frame.x0, y, f"LANDING BEAM: {landing_beam}")
    y -= 10
    for w in warn:
        c.setFillColor(HexColor("#CC6600"))
        c.drawString(frame.x0, y, f"NOTE: {w}")
        c.setFillColor(HexColor("#000000"))
        y -= 9

    y -= 6
    y = _draw_stair_schedule(
        c,
        frame.x0,
        y,
        storey_h_m,
        riser_count,
        riser_mm,
        going_mm,
        waist_mm,
        main_dia,
        main_sp,
        main_nom,
        dist_dia,
        dist_sp,
        dist_nom,
        landing_beam,
    )

    _finish_page(c, model, page_w, "S-12")
    return 1


def _stair_design_dict(model: StructuralModel) -> dict:
    data = model.structapi_data or {}
    for key in ("staircase", "stair", "stairs"):
        d = data.get(key)
        if isinstance(d, dict):
            return d
    return {}


def _draw_stair_section(
    c: canvas.Canvas,
    x0: float,
    y0: float,
    w: float,
    h: float,
    n_treads: int,
    n_risers: int,
    riser_mm: float,
    going_mm: float,
    waist_mm: float,
    landing_w_m: float,
    main_dia: int,
    main_sp: int,
    main_nom: bool,
    dist_dia: int,
    dist_sp: int,
    dist_nom: bool,
) -> float:
    """Draw the flight section and its callouts; returns the y below the
    lowest line drawn, so the caller can continue under it."""
    c.setFont("Helvetica-Bold", 6)
    c.drawString(x0, y0 + h - 8, "SECTION THROUGH FLIGHT")

    # a flight of n_treads treads has n_risers = n_treads + 1 risers — the
    # last riser lands on the landing itself with no going of its own, so
    # n_risers * riser_mm reproduces the full floor-to-floor height exactly.
    total_run_mm = n_treads * going_mm
    total_rise_mm = n_risers * riser_mm
    scale_pt, denom = fit_detail_scale(
        total_run_mm + landing_w_m * 1000, total_rise_mm + 200, w - 10, h - 40
    )

    ox = x0 + 5
    oy = y0 + 10
    step_w = going_mm * scale_pt
    step_h = riser_mm * scale_pt

    # waist slab as an inclined hatched band under the steps
    waist_pt = waist_mm * scale_pt
    run_pt = total_run_mm * scale_pt
    rise_pt = (n_treads * riser_mm) * scale_pt
    perp = math.hypot(run_pt, rise_pt) or 1.0
    dx, dy = -rise_pt / perp * waist_pt, run_pt / perp * waist_pt
    waist_pts = [
        (ox, oy),
        (ox + run_pt, oy + rise_pt),
        (ox + run_pt + dx, oy + rise_pt + dy),
        (ox + dx, oy + dy),
    ]
    hatch_polygon(c, waist_pts, "rcc", spacing_pt=3.0)
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.6)
    p = c.beginPath()
    p.moveTo(*waist_pts[0])
    for pt in waist_pts[1:]:
        p.lineTo(*pt)
    p.close()
    c.drawPath(p, fill=0, stroke=1)

    # steps on top of the waist
    cx, cy = ox, oy
    for _ in range(n_treads):
        c.line(cx, cy, cx, cy + step_h)
        c.line(cx, cy + step_h, cx + step_w, cy + step_h)
        cx += step_w
        cy += step_h
    # final riser rises straight to landing level with no going of its own
    c.line(cx, cy, cx, cy + step_h)
    cy += step_h

    # landing at the top
    landing_pt = landing_w_m * 1000 * scale_pt
    c.rect(cx, cy - step_h * 0.15, landing_pt, step_h * 1.15, fill=0, stroke=1)
    c.setFont("Helvetica", 4.5)
    c.drawString(cx, cy + step_h * 1.3, "LANDING")

    # main steel bent up along the waist, distribution perpendicular
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.5)
    off = waist_pt * 0.3
    c.line(
        ox + off * dx / waist_pt if waist_pt else ox,
        oy + off * dy / waist_pt if waist_pt else oy,
        ox + run_pt + off * dx / waist_pt if waist_pt else ox + run_pt,
        oy + rise_pt + off * dy / waist_pt if waist_pt else oy + rise_pt,
    )

    # One stack, one leading. These were previously two independent stacks
    # anchored at the box origin and at the flight origin, which sit at
    # roughly the same height — so the five lines printed on top of each
    # other. Returns the bottom so the caller can flow below it instead of
    # guessing a fixed offset.
    callouts = [
        (
            "Helvetica",
            4.5,
            f"{n_risers} RISERS @ {riser_mm:.0f} = {total_rise_mm:.0f}mm",
        ),
        (
            "Helvetica",
            4.5,
            f"GOING {going_mm:.0f}mm  WAIST {waist_mm:.0f}mm  "
            f"F2F HT {total_rise_mm:.0f}mm",
        ),
        (
            "Helvetica-Bold",
            5,
            "MAIN: "
            + _callout(
                main_dia, main_sp, "ALONG WAIST, BENT UP OVER LANDING BEAM", main_nom
            ),
        ),
        (
            "Helvetica",
            5,
            "DIST: " + _callout(dist_dia, dist_sp, "PERPENDICULAR TO MAIN", dist_nom),
        ),
    ]
    c.setFillColor(HexColor("#000000"))
    ty = y0 - 6.0
    for font, size, text in callouts:
        c.setFont(font, size)
        c.drawString(x0, ty, text)
        ty -= 8.0
    draw_scale_note(c, x0, ty, denom)
    return ty - 8.0


def _draw_stair_plan(
    c: canvas.Canvas,
    x0: float,
    y0: float,
    w: float,
    h: float,
    room,
    stair,
    landing_w_m: float,
) -> None:
    c.setFont("Helvetica-Bold", 6)
    c.drawString(x0, y0 + h - 8, "PLAN OF FLIGHT")

    scale_pt, denom = fit_detail_scale(
        room.width * 1000, room.depth * 1000, w - 10, h - 40
    )
    rw, rh = room.width * 1000 * scale_pt, room.depth * 1000 * scale_pt
    px0, py0 = x0 + 5, y0 + 10

    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.6)
    c.rect(px0, py0, rw, rh, fill=0, stroke=1)

    vertical_run = room.depth >= room.width
    n = max(stair.tread_count, 1)
    spacing = (rh if vertical_run else rw) / (n + 1)
    c.setLineWidth(0.3)
    for i in range(1, n + 1):
        t = spacing * i
        if vertical_run:
            c.line(px0, py0 + t, px0 + rw, py0 + t)
        else:
            c.line(px0 + t, py0, px0 + t, py0 + rh)

    landing_pt = landing_w_m * 1000 * scale_pt
    if vertical_run:
        c.rect(px0, py0 + rh - landing_pt, rw, landing_pt, fill=0, stroke=1)
    else:
        c.rect(px0 + rw - landing_pt, py0, landing_pt, rh, fill=0, stroke=1)

    c.setFont("Helvetica", 4.5)
    c.drawString(px0, py0 - 8, f"{n} TREADS SHOWN, LANDING {landing_w_m:.2f}m WIDE")
    draw_scale_note(c, px0, py0 - 16, denom)


def _draw_stair_schedule(
    c: canvas.Canvas,
    x: float,
    y_top: float,
    storey_h_m: float,
    n_risers: int,
    riser_mm: float,
    going_mm: float,
    waist_mm: float,
    main_dia: int,
    main_sp: int,
    main_nom: bool,
    dist_dia: int,
    dist_sp: int,
    dist_nom: bool,
    landing_beam: str,
) -> float:
    headers = (
        "F2F HT",
        "RISERS",
        "RISER",
        "GOING",
        "WAIST",
        "MAIN STEEL",
        "DIST STEEL",
    )
    col_ws = (48.0, 40.0, 40.0, 40.0, 40.0, 100.0, 100.0)
    rows = [
        (
            f"{storey_h_m * 1000:.0f}mm",
            str(n_risers),
            f"{riser_mm:.0f}mm",
            f"{going_mm:.0f}mm",
            f"{waist_mm:.0f}mm",
            _callout(main_dia, main_sp, "", main_nom),
            _callout(dist_dia, dist_sp, "", dist_nom),
        )
    ]
    height = _draw_generic_schedule_table(
        c, "STAIRCASE SCHEDULE", headers, col_ws, rows, x, y_top
    )
    return y_top - height


# ── shared frame/finish ──────────────────────────────────────────────────────


def _frame(c: canvas.Canvas, drg_no: str, *, continued: bool = False) -> DetailFrame:
    from app.engine.structural_sheet import detail_sheet_frame

    return detail_sheet_frame(
        c, heading=SHEET_TITLES[drg_no], drg_no=drg_no, continued=continued
    )


def _finish_page(
    c: canvas.Canvas, model: StructuralModel, page_w: float, drg_no: str
) -> None:
    structural_title_block(
        c,
        project_name=model.project_name,
        cfg=model.cfg,
        drg_no=drg_no,
        sheet_title=SHEET_TITLES[drg_no],
        page_w=page_w,
        scale_text="AS NOTED",
        layout_label=model.layout_label,
    )
    draw_disclaimer(c, model.disclaimer, MARGIN, MARGIN - 8)
