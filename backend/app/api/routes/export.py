from decimal import Decimal
from io import BytesIO

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

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6  # metres

    # Define layers
    layer_defs = [
        ("A-WALL-BRICK", colors.RED,    0.50),
        ("A-WALL-INT",   colors.YELLOW, 0.35),
        ("A-DOOR",       colors.CYAN,   0.25),
        ("A-WINDOW",     colors.BLUE,   0.25),
        ("S-COLUMN",     colors.WHITE,  0.35),
        ("S-BEAM",       colors.WHITE,  0.35),
        ("S-GRID",       colors.GRAY,   0.18),
        ("DIM-LINE",     colors.GRAY,   0.18),
        ("TEXT",         colors.WHITE,  0.18),
    ]
    for lname, color, lw in layer_defs:
        layer = doc.layers.new(lname)
        layer.color = color
        layer.lineweight = int(lw * 100)

    msp = doc.modelspace()

    ewt = 0.23
    iwt = 0.115

    for floor_plan in [layout.ground_floor, layout.first_floor]:
        z_offset = 0.0 if floor_plan.floor == 0 else 3.0  # first floor elevated 3 m

        # ── Rooms as closed polylines ────────────────────────────────────────
        for room in floor_plan.rooms:
            pts = [
                (room.x, room.y, z_offset),
                (room.x + room.width, room.y, z_offset),
                (room.x + room.width, room.y + room.depth, z_offset),
                (room.x, room.y + room.depth, z_offset),
            ]
            layer = "A-WALL-BRICK" if room.type in ("living", "bedroom", "kitchen") else "A-WALL-INT"
            msp.add_lwpolyline(
                [(p[0], p[1]) for p in pts],
                close=True,
                dxfattribs={"layer": layer, "elevation": z_offset},
            )
            # Room label
            cx = room.x + room.width / 2
            cy = room.y + room.depth / 2
            msp.add_text(
                f"{room.name}\n{room.area}m²",
                dxfattribs={
                    "layer": "TEXT",
                    "height": 0.25,
                    "insert": (cx, cy, z_offset),
                    "halign": 1,
                    "valign": 2,
                },
            )

        # ── Columns ─────────────────────────────────────────────────────────
        half = 0.15  # 300 mm / 2
        seen = set()
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
        rooms = floor_plan.rooms
        if rooms:
            min_x = min(r.x for r in rooms)
            max_x = max(r.x + r.width for r in rooms)
            min_y = min(r.y for r in rooms)
            max_y = max(r.y + r.depth for r in rooms)

            # Width dimension below
            dim_offset = 1.5
            msp.add_linear_dim(
                base=(min_x, min_y - dim_offset, z_offset),
                p1=(min_x, min_y, z_offset),
                p2=(max_x, min_y, z_offset),
                angle=0,
                dxfattribs={"layer": "DIM-LINE"},
            )
            # Depth dimension left
            msp.add_linear_dim(
                base=(min_x - dim_offset, min_y, z_offset),
                p1=(min_x, min_y, z_offset),
                p2=(min_x, max_y, z_offset),
                angle=90,
                dxfattribs={"layer": "DIM-LINE"},
            )

    # Title annotation in modelspace
    msp.add_text(
        f"PlanForge | {project_name} | Layout {layout.id} — {layout.name}",
        dxfattribs={"layer": "TEXT", "height": 0.5, "insert": (0, -3, 0)},
    )

    buf = BytesIO()
    doc.write(buf)
    return buf.getvalue()


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
