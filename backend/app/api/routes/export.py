import json as _json
from decimal import Decimal
from io import BytesIO, StringIO

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.engine.boq import QuantityEngine
from app.engine.generator import generate
from app.engine.models import PlotConfig
from app.engine.pdf import render_pdf
from app.models.project import Project
from app.models.user import User

router = APIRouter()


async def _get_plan_tier(user_id: str, db: AsyncSession) -> str:
    result = await db.execute(select(User).where(User.id == user_id))
    u = result.scalar_one_or_none()
    return u.plan_tier if u else "free"


def _to_float(v) -> float:
    return float(v) if isinstance(v, Decimal) else v


def _user_id(x_user_id: str = Header(..., alias="X-User-Id")) -> str:
    return x_user_id


def _cfg_from_project(project: Project) -> PlotConfig:
    return PlotConfig(
        plot_length=_to_float(project.plot_length),
        plot_width=_to_float(project.plot_width),
        setback_front=_to_float(project.setback_front),
        setback_rear=_to_float(project.setback_rear),
        setback_left=_to_float(project.setback_left),
        setback_right=_to_float(project.setback_right),
        num_bedrooms=project.num_bedrooms,
        toilets=project.toilets,
        parking=project.parking,
        city=getattr(project, "city", "other") or "other",
        vastu_enabled=getattr(project, "vastu_enabled", False) or False,
        road_width_m=_to_float(getattr(project, "road_width_m", 9.0) or 9.0),
        road_side=getattr(project, "road_side", "S") or "S",
        has_pooja=getattr(project, "has_pooja", False) or False,
        has_study=getattr(project, "has_study", False) or False,
        has_balcony=getattr(project, "has_balcony", False) or False,
        plot_shape=getattr(project, "plot_shape", "rectangular") or "rectangular",
        plot_front_width=_to_float(getattr(project, "plot_front_width", 0.0) or 0.0),
        plot_rear_width=_to_float(getattr(project, "plot_rear_width", 0.0) or 0.0),
        plot_side_offset=_to_float(getattr(project, "plot_side_offset", 0.0) or 0.0),
        plot_corners=_json.loads(project.plot_corners) if getattr(project, "plot_corners", None) else None,
    )


async def _get_project(project_id: str, user_id: str, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


# ── PDF export ────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/export/pdf")
async def export_pdf(
    project_id: str,
    layout_id: str = "A",
    user_id: str = Depends(_user_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    project = await _get_project(project_id, user_id, db)
    cfg = _cfg_from_project(project)

    layouts = generate(cfg)
    layout = next((lay for lay in layouts if lay.id == layout_id), None)
    if layout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Layout {layout_id!r} not found")

    pdf_bytes = render_pdf(project.name, layout, cfg, project.num_bedrooms)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                f'attachment; filename="planforge-{project_id}-layout-{layout_id}.pdf"'
        },
    )


# ── DXF export ────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/export/dxf")
async def export_dxf(
    project_id: str,
    layout_id: str = "A",
    user_id: str = Depends(_user_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    plan = await _get_plan_tier(user_id, db)
    if plan not in ("basic", "pro"):
        raise HTTPException(status_code=402, detail="DXF export requires Basic or Pro plan.")

    try:
        import ezdxf
    except ImportError:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED,
                            detail="ezdxf not installed. Run: uv add ezdxf")

    project = await _get_project(project_id, user_id, db)
    cfg = _cfg_from_project(project)

    layouts = generate(cfg)
    layout = next((lay for lay in layouts if lay.id == layout_id), None)
    if layout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Layout {layout_id!r} not found")

    dxf_bytes = _render_dxf(project.name, layout, cfg)

    return Response(
        content=dxf_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition":
                f'attachment; filename="planforge-{project_id}-layout-{layout_id}.dxf"'
        },
    )


def _render_dxf(project_name: str, layout, cfg: PlotConfig) -> bytes:
    import ezdxf
    from ezdxf import colors
    from ezdxf.enums import TextEntityAlignment

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6  # metres

    layer_defs = [
        ("PLOT-BOUNDARY", colors.GREEN,  0.25),
        ("A-WALL-BRICK",  colors.RED,    0.50),
        ("A-WALL-INT",    colors.YELLOW, 0.35),
        ("A-DOOR",        colors.CYAN,   0.25),
        ("A-WINDOW",      colors.BLUE,   0.25),
        ("S-COLUMN",      colors.WHITE,  0.35),
        ("S-BEAM",        colors.WHITE,  0.35),
        ("S-GRID",        colors.GRAY,   0.18),
        ("DIM-LINE",      colors.GRAY,   0.18),
        ("TEXT",          colors.WHITE,  0.18),
    ]
    for lname, color, lw in layer_defs:
        layer = doc.layers.new(lname)
        layer.color = color
        layer.lineweight = int(lw * 100)

    msp = doc.modelspace()

    # ── Plot boundary ─────────────────────────────────────────────────────────
    if cfg.plot_shape == "quadrilateral" and cfg.plot_corners and len(cfg.plot_corners) == 4:
        boundary_pts = [(float(x), float(y)) for x, y in cfg.plot_corners]
    else:
        boundary_pts = [
            (0.0, 0.0),
            (cfg.plot_width, 0.0),
            (cfg.plot_width, cfg.plot_length),
            (0.0, cfg.plot_length),
        ]
    msp.add_lwpolyline(
        boundary_pts,
        close=True,
        dxfattribs={"layer": "PLOT-BOUNDARY", "linetype": "DASHED"},
    )

    # Collect all floor plans (including optional second/basement floors)
    floor_plans = [layout.ground_floor, layout.first_floor]
    if layout.second_floor:
        floor_plans.append(layout.second_floor)
    if layout.basement_floor:
        floor_plans.append(layout.basement_floor)

    import math
    from app.engine.cad_elements import build_walls_from_rooms, build_windows

    ewt_m = 0.23   # external wall thickness (m)
    iwt_m = 0.115  # internal (half-brick) wall thickness

    for floor_plan in floor_plans:
        z_offset = float(floor_plan.floor) * 3.0
        rooms = floor_plan.rooms
        if not rooms:
            continue

        # Buildable bounds derived from actual room extents
        bld_x = min(r.x for r in rooms)
        bld_y = min(r.y for r in rooms)
        bld_w = max(r.x + r.width  for r in rooms) - bld_x
        bld_d = max(r.y + r.depth  for r in rooms) - bld_y

        # ── 2A: Double-line walls ────────────────────────────────────────────
        walls = build_walls_from_rooms(rooms, ewt_m, iwt_m, bld_x, bld_y, bld_w, bld_d)
        for wall in walls:
            dx = wall.x2 - wall.x1
            dy = wall.y2 - wall.y1
            seg_len = math.hypot(dx, dy)
            if seg_len < 0.001:
                continue
            px, py = -dy / seg_len, dx / seg_len  # perpendicular unit vector
            h = wall.thickness / 2
            layer = "A-WALL-BRICK" if wall.thickness >= ewt_m else "A-WALL-INT"
            msp.add_line(
                (wall.x1 + h * px, wall.y1 + h * py, z_offset),
                (wall.x2 + h * px, wall.y2 + h * py, z_offset),
                dxfattribs={"layer": layer},
            )
            msp.add_line(
                (wall.x1 - h * px, wall.y1 - h * py, z_offset),
                (wall.x2 - h * px, wall.y2 - h * py, z_offset),
                dxfattribs={"layer": layer},
            )

        # ── 2B: Door symbols (line + arc at room adjacencies) ───────────────
        door_w = 0.9
        placed_doors: set = set()
        for i, ra in enumerate(rooms):
            for j, rb in enumerate(rooms):
                if j <= i:
                    continue
                # Vertical shared wall: ra right-edge ≈ rb left-edge
                if abs(ra.x + ra.width - rb.x) < 0.05:
                    y_lo = max(ra.y, rb.y)
                    y_hi = min(ra.y + ra.depth, rb.y + rb.depth)
                    if y_hi - y_lo > door_w + 0.1:
                        wx = ra.x + ra.width
                        my = (y_lo + y_hi) / 2
                        key = (round(wx, 2), round(my, 2), "v")
                        if key not in placed_doors:
                            placed_doors.add(key)
                            hy = my - door_w / 2
                            msp.add_line((wx, hy, z_offset), (wx, hy + door_w, z_offset), dxfattribs={"layer": "A-DOOR"})
                            msp.add_arc(center=(wx, hy), radius=door_w, start_angle=90, end_angle=180, dxfattribs={"layer": "A-DOOR", "elevation": z_offset})
                elif abs(rb.x + rb.width - ra.x) < 0.05:
                    y_lo = max(ra.y, rb.y)
                    y_hi = min(ra.y + ra.depth, rb.y + rb.depth)
                    if y_hi - y_lo > door_w + 0.1:
                        wx = rb.x + rb.width
                        my = (y_lo + y_hi) / 2
                        key = (round(wx, 2), round(my, 2), "v")
                        if key not in placed_doors:
                            placed_doors.add(key)
                            hy = my - door_w / 2
                            msp.add_line((wx, hy, z_offset), (wx, hy + door_w, z_offset), dxfattribs={"layer": "A-DOOR"})
                            msp.add_arc(center=(wx, hy + door_w), radius=door_w, start_angle=270, end_angle=360, dxfattribs={"layer": "A-DOOR", "elevation": z_offset})
                # Horizontal shared wall: ra top ≈ rb bottom
                if abs(ra.y + ra.depth - rb.y) < 0.05:
                    x_lo = max(ra.x, rb.x)
                    x_hi = min(ra.x + ra.width, rb.x + rb.width)
                    if x_hi - x_lo > door_w + 0.1:
                        wy = ra.y + ra.depth
                        mx = (x_lo + x_hi) / 2
                        key = (round(mx, 2), round(wy, 2), "h")
                        if key not in placed_doors:
                            placed_doors.add(key)
                            hx = mx - door_w / 2
                            msp.add_line((hx, wy, z_offset), (hx + door_w, wy, z_offset), dxfattribs={"layer": "A-DOOR"})
                            msp.add_arc(center=(hx, wy), radius=door_w, start_angle=0, end_angle=90, dxfattribs={"layer": "A-DOOR", "elevation": z_offset})
                elif abs(rb.y + rb.depth - ra.y) < 0.05:
                    x_lo = max(ra.x, rb.x)
                    x_hi = min(ra.x + ra.width, rb.x + rb.width)
                    if x_hi - x_lo > door_w + 0.1:
                        wy = rb.y + rb.depth
                        mx = (x_lo + x_hi) / 2
                        key = (round(mx, 2), round(wy, 2), "h")
                        if key not in placed_doors:
                            placed_doors.add(key)
                            hx = mx - door_w / 2
                            msp.add_line((hx, wy, z_offset), (hx + door_w, wy, z_offset), dxfattribs={"layer": "A-DOOR"})
                            msp.add_arc(center=(hx + door_w, wy), radius=door_w, start_angle=90, end_angle=180, dxfattribs={"layer": "A-DOOR", "elevation": z_offset})

        # ── 2C: Window symbols (3 parallel lines on exterior walls) ─────────
        windows = build_windows(rooms, bld_x, bld_y, bld_w, bld_d)
        win_gap = 0.04  # 40 mm between the 3 window lines
        for win in windows:
            hw = win.width / 2
            if win.is_horizontal:
                for off in (-win_gap, 0.0, win_gap):
                    msp.add_line(
                        (win.cx - hw, win.cy + off, z_offset),
                        (win.cx + hw, win.cy + off, z_offset),
                        dxfattribs={"layer": "A-WINDOW"},
                    )
            else:
                for off in (-win_gap, 0.0, win_gap):
                    msp.add_line(
                        (win.cx + off, win.cy - hw, z_offset),
                        (win.cx + off, win.cy + hw, z_offset),
                        dxfattribs={"layer": "A-WINDOW"},
                    )

        # ── Room labels ──────────────────────────────────────────────────────
        for room in rooms:
            cx = room.x + room.width / 2
            cy = room.y + room.depth / 2
            msp.add_mtext(
                f"{room.name}\\P{room.area}m²",
                dxfattribs={
                    "layer": "TEXT",
                    "char_height": 0.25,
                    "insert": (cx, cy, z_offset),
                    "attachment_point": 5,  # MIDDLE_CENTER
                },
            )

        # ── Columns ──────────────────────────────────────────────────────────
        half = 0.15
        seen: set = set()
        for col in floor_plan.columns:
            key = (round(col.x, 2), round(col.y, 2))
            if key in seen:
                continue
            seen.add(key)
            pts_col = [
                (col.x - half, col.y - half),
                (col.x + half, col.y - half),
                (col.x + half, col.y + half),
                (col.x - half, col.y + half),
            ]
            msp.add_lwpolyline(
                pts_col,
                close=True,
                dxfattribs={"layer": "S-COLUMN", "elevation": z_offset},
            )

        # ── Overall dimension lines ──────────────────────────────────────────
        min_x = min(r.x for r in rooms)
        max_x = max(r.x + r.width  for r in rooms)
        min_y = min(r.y for r in rooms)
        max_y = max(r.y + r.depth  for r in rooms)
        dim_offset = 1.5
        msp.add_linear_dim(
            base=(min_x, min_y - dim_offset),
            p1=(min_x, min_y),
            p2=(max_x, min_y),
            angle=0,
            dxfattribs={"layer": "DIM-LINE"},
        ).render()
        msp.add_linear_dim(
            base=(min_x - dim_offset, min_y),
            p1=(min_x, min_y),
            p2=(min_x, max_y),
            angle=90,
            dxfattribs={"layer": "DIM-LINE"},
        ).render()

    # Title annotation
    msp.add_mtext(
        f"PlanForge | {project_name} | Layout {layout.id} — {layout.name}",
        dxfattribs={"layer": "TEXT", "char_height": 0.5, "insert": (0, -3, 0)},
    )

    # ezdxf writes DXF as text (not binary) — use StringIO then encode
    text_buf = StringIO()
    doc.write(text_buf)
    return text_buf.getvalue().encode("utf-8")


# ── BOQ export ────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/boq")
async def export_boq(
    project_id: str,
    layout_id: str = "A",
    fmt: str = "json",
    user_id: str = Depends(_user_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    project = await _get_project(project_id, user_id, db)
    cfg = _cfg_from_project(project)

    layouts = generate(cfg)
    layout = next((lay for lay in layouts if lay.id == layout_id), None)
    if layout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Layout {layout_id!r} not found")

    engine = QuantityEngine()
    boq = engine.calculate(layout, cfg, project_name=project.name)

    if fmt == "excel":
        plan = await _get_plan_tier(user_id, db)
        if plan != "pro":
            raise HTTPException(status_code=402, detail="BOQ Excel export requires Pro plan.")
        return _boq_excel_response(boq, project_id, layout_id)

    import json
    return Response(
        content=json.dumps(boq.to_dict(), indent=2),
        media_type="application/json",
    )


def _boq_excel_response(boq, project_id: str, layout_id: str) -> Response:
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED,
                            detail="openpyxl not installed. Run: uv add openpyxl")

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "BOQ"

    # Header
    ws.merge_cells("A1:E1")
    ws["A1"] = f"Bill of Quantities — {boq.project_name} / Layout {boq.layout_id}"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A1"].alignment = Alignment(horizontal="center")

    # Column headers
    headers = ["S.No", "Item Description", "Quantity", "Unit", "Rate (₹)", "Amount (₹)"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1E3A5F")
        cell.alignment = Alignment(horizontal="center")

    # Data rows
    for row_idx, item in enumerate(boq.line_items, start=4):
        ws.cell(row=row_idx, column=1, value=item.item)
        ws.cell(row=row_idx, column=2, value=item.description)
        ws.cell(row=row_idx, column=3, value=item.quantity)
        ws.cell(row=row_idx, column=4, value=item.unit)
        ws.cell(row=row_idx, column=5, value="")   # rate — user fills
        ws.cell(row=row_idx, column=6, value="")   # amount — user fills

    # Auto-width columns
    for col in ws.columns:
        max_len = max((len(str(cell.value or "")) for cell in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = max(max_len + 2, 12)

    # Footer note
    note_row = len(boq.line_items) + 5
    ws.cell(row=note_row, column=1, value="Note: Quantities are approximate. "
            "Verify with site measurements before procurement.")
    ws.cell(row=note_row, column=1).font = Font(italic=True, color="888888")
    ws.cell(row=note_row + 1, column=1, value="Generated by PlanForge")

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition":
                f'attachment; filename="planforge-boq-{project_id}-{layout_id}.xlsx"'
        },
    )
