import math

from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfgen.pathobject import PDFPathObject

from app.engine.section_geometry import (
    ElevationDrawing,
    LevelMark,
    SectionDrawing,
    VDim,
)

CUT_LW = 1.4  # cut-element outline (IS 962 thick)
THIN_LW = 0.5  # annotation / beyond / dimension lines
PT_PER_M_REAL = 72 / 0.0254  # points per real-world metre (for 1:N ratio)


def hatch_polygon(
    c: Canvas,
    pts: list[tuple[float, float]],
    material: str,
    spacing_pt: float = 5.0,
) -> None:
    if spacing_pt <= 0:
        raise ValueError("spacing_pt must be positive")
    if len(pts) < 3:
        return
    c.saveState()
    p = c.beginPath()
    p.moveTo(pts[0][0], pts[0][1])
    for q in pts[1:]:
        p.lineTo(q[0], q[1])
    p.close()
    c.clipPath(p, stroke=0, fill=0)
    xs = [q[0] for q in pts]
    ys = [q[1] for q in pts]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    rise = y1 - y0
    c.setStrokeColorRGB(0, 0, 0)
    c.setFillColorRGB(0, 0, 0)
    c.setLineWidth(0.3)
    if material in ("brick", "rcc"):
        t = x0 - rise
        while t < x1:
            c.line(t, y0, t + rise, y1)
            t += spacing_pt
    if material == "rcc":
        t = x0
        while t < x1 + rise:
            c.line(t, y0, t - rise, y1)
            t += spacing_pt
    elif material == "pcc":
        yy = y0 + spacing_pt / 2
        while yy < y1:
            xx = x0 + spacing_pt / 2
            while xx < x1:
                c.circle(xx, yy, 0.4, stroke=0, fill=1)
                xx += spacing_pt
            yy += spacing_pt
    elif material == "earth":
        dx = 3.0 * math.cos(math.radians(60))
        dy = 3.0 * math.sin(math.radians(60))
        row = 0
        yy = y0 + spacing_pt / 2
        while yy < y1:
            xx = x0 + (spacing_pt / 2 if row % 2 else 0.0)
            while xx < x1:
                c.line(xx, yy, xx + dx, yy + dy)
                xx += spacing_pt
            yy += spacing_pt
            row += 1
    c.restoreState()


def _fit(
    bounds: tuple[float, float, float, float],
    region: tuple[float, float, float, float],
) -> tuple[float, float, float]:
    x, y, w, h = region
    s0, z0, s1, z1 = bounds
    scale = min(w / (s1 - s0), h / (z1 - z0)) * 0.92
    tx = x + (w - (s1 - s0) * scale) / 2 - s0 * scale
    ty = y + (h - (z1 - z0) * scale) / 2 - z0 * scale
    return scale, tx, ty


def _draw_levels(
    c: Canvas, levels: list[LevelMark], scale: float, tx: float, ty: float
) -> None:
    c.setStrokeColorRGB(0, 0, 0)
    c.setFillColorRGB(0, 0, 0)
    c.setLineWidth(THIN_LW)
    c.setFont("Helvetica", 6)
    for lv in levels:
        px, py = tx + lv.s * scale, ty + lv.z * scale
        c.line(px - 8, py, px, py)
        p = c.beginPath()
        p.moveTo(px, py)
        p.lineTo(px - 3, py + 5)
        p.lineTo(px + 3, py + 5)
        p.close()
        c.drawPath(p, fill=1, stroke=0)
        c.drawString(px + 4, py + 1, lv.label)


def _draw_vdims(
    c: Canvas, vdims: list[VDim], x_dim: float, scale: float, ty: float
) -> None:
    c.setStrokeColorRGB(0, 0, 0)
    c.setFillColorRGB(0, 0, 0)
    c.setLineWidth(THIN_LW)
    c.setFont("Helvetica", 5.5)
    for d in vdims:
        y1p, y2p = ty + d.z1 * scale, ty + d.z2 * scale
        c.line(x_dim - 3, y1p, x_dim + 3, y1p)
        c.line(x_dim - 3, y2p, x_dim + 3, y2p)
        c.line(x_dim, y1p, x_dim, y2p)
        c.line(x_dim - 3.5, y1p - 3.5, x_dim + 3.5, y1p + 3.5)
        c.line(x_dim - 3.5, y2p - 3.5, x_dim + 3.5, y2p + 3.5)
        c.saveState()
        c.translate(x_dim - 4, (y1p + y2p) / 2)
        c.rotate(90)
        c.drawCentredString(0, 0, d.label)
        c.restoreState()


def _draw_scale_bar(
    c: Canvas, x: float, y: float, scale: float, denom: int, metres: int = 4
) -> None:
    h = 4.0
    c.setLineWidth(0.6)
    c.setStrokeColorRGB(0, 0, 0)
    for i in range(metres):
        c.setFillColorRGB(0, 0, 0) if i % 2 == 0 else c.setFillColorRGB(1, 1, 1)
        c.rect(x + i * scale, y, scale, h, fill=1, stroke=1)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 5)
    for i in range(metres + 1):
        c.drawCentredString(x + i * scale, y + h + 2, "0" if i == 0 else f"{i}M")
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(x + metres * scale / 2, y + h + 9, f"SCALE 1:{denom}")


def _poly_path(c: Canvas, pts: list[tuple[float, float]]) -> PDFPathObject:
    p = c.beginPath()
    p.moveTo(pts[0][0], pts[0][1])
    for q in pts[1:]:
        p.lineTo(q[0], q[1])
    p.close()
    return p


def _draw_title(
    c: Canvas, region: tuple[float, float, float, float], title: str
) -> None:
    x, y, w, _ = region
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 9)
    # above the scale bar's label row so long bars can't collide with the text
    c.drawCentredString(x + w / 2, y + 22, title)


def render_section_view(
    c: Canvas, sd: SectionDrawing, region: tuple[float, float, float, float]
) -> float:
    scale, tx, ty = _fit(sd.bounds, region)
    c.saveState()
    c.setStrokeColorRGB(0, 0, 0)
    for sp in sd.polys:
        pts = [(tx + s * scale, ty + z * scale) for s, z in sp.poly.exterior.coords]
        c.setFillColorRGB(1, 1, 1)
        c.setLineWidth(CUT_LW if sp.cut else THIN_LW)
        c.drawPath(_poly_path(c, pts), fill=1, stroke=1)
        hatch_polygon(c, pts, sp.material)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 5.5)
    for s, z, text in sd.labels:
        c.drawCentredString(tx + s * scale, ty + z * scale, text)
    _draw_levels(c, sd.levels, scale, tx, ty)
    _draw_vdims(c, sd.vdims, tx + sd.bounds[0] * scale + 10, scale, ty)
    denom = round(PT_PER_M_REAL / scale)
    _draw_scale_bar(c, region[0] + 8, region[1] + 4, scale, denom)
    _draw_title(c, region, sd.title)
    c.restoreState()
    return scale


def render_elevation_view(
    c: Canvas, ed: ElevationDrawing, region: tuple[float, float, float, float]
) -> float:
    scale, tx, ty = _fit(ed.bounds, region)
    minx, _, maxx, _ = ed.silhouette.bounds
    c.saveState()
    c.setStrokeColorRGB(0, 0, 0)
    pts = [(tx + u * scale, ty + z * scale) for u, z in ed.silhouette.exterior.coords]
    c.setFillColorRGB(1, 1, 1)
    c.setLineWidth(1.0)
    c.drawPath(_poly_path(c, pts), fill=1, stroke=1)
    c.setLineWidth(CUT_LW)
    gl_y = ty + ed.gl_z * scale
    c.line(tx + (minx - 0.8) * scale, gl_y, tx + (maxx + 0.8) * scale, gl_y)
    c.saveState()
    c.setLineWidth(THIN_LW)
    c.setDash(3, 3)
    for s1, z1, s2, z2 in ed.ref_lines:
        c.line(tx + s1 * scale, ty + z1 * scale, tx + s2 * scale, ty + z2 * scale)
    c.restoreState()
    c.setLineWidth(THIN_LW)
    for rect in ed.openings + ed.chajjas:
        rpts = [(tx + u * scale, ty + z * scale) for u, z in rect.exterior.coords]
        c.drawPath(_poly_path(c, rpts), fill=0, stroke=1)
    _draw_levels(c, ed.levels, scale, tx, ty)
    _draw_vdims(c, ed.vdims, tx + ed.bounds[0] * scale + 10, scale, ty)
    denom = round(PT_PER_M_REAL / scale)
    _draw_scale_bar(c, region[0] + 8, region[1] + 4, scale, denom)
    _draw_title(c, region, ed.title)
    c.restoreState()
    return scale


def draw_section_marker(
    c: Canvas, x1: float, y1: float, x2: float, y2: float, label: str = "A"
) -> None:
    dx, dy = x2 - x1, y2 - y1
    ln = math.hypot(dx, dy)
    if ln < 1e-9:
        return
    ux, uy = dx / ln, dy / ln
    vx, vy = -uy, ux  # view direction (perpendicular)
    c.saveState()
    c.setStrokeColorRGB(0, 0, 0)
    c.setFillColorRGB(0, 0, 0)
    c.setLineWidth(0.5)
    c.setDash([6, 2, 1, 2], 0)
    c.line(x1, y1, x2, y2)
    c.setDash([], 0)
    c.setLineWidth(2.0)
    c.line(x1, y1, x1 + ux * 8, y1 + uy * 8)
    c.line(x2 - ux * 8, y2 - uy * 8, x2, y2)
    for ex, ey in ((x1, y1), (x2, y2)):
        p = c.beginPath()
        p.moveTo(ex + vx * 7, ey + vy * 7)
        p.lineTo(ex - ux * 3, ey - uy * 3)
        p.lineTo(ex + ux * 3, ey + uy * 3)
        p.close()
        c.drawPath(p, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(x1 - ux * 12, y1 - uy * 12 - 3, label)
    c.drawCentredString(x2 + ux * 12, y2 + uy * 12 - 3, label)
    c.restoreState()
