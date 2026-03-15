import json as _json
from decimal import Decimal
from io import BytesIO, StringIO

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.engine.approval_pdf import OwnerInfo, generate_approval_pdf
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

    annotations = getattr(project, "annotations", None) or {}
    pdf_bytes = render_pdf(project.name, layout, cfg, project.num_bedrooms, annotations=annotations or None)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                f'attachment; filename="planforge-{project_id}-layout-{layout_id}.pdf"'
        },
    )


# ── Approval PDF export ───────────────────────────────────────────────────────

class ApprovalPdfRequest(BaseModel):
    owner_name: str
    survey_number: str
    locality: str
    engineer_name: str
    license_number: str
    municipality: str | None = None


@router.post("/projects/{project_id}/export/approval-pdf")
async def export_approval_pdf(
    project_id: str,
    body: ApprovalPdfRequest,
    layout_id: str = "A",
    user_id: str = Depends(_user_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    project = await _get_project(project_id, user_id, db)
    cfg = _cfg_from_project(project)

    layouts = generate(cfg)
    layout = next((lay for lay in layouts if lay.id == layout_id), None)
    if layout is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Layout {layout_id!r} not found",
        )

    municipality = body.municipality or getattr(project, "municipality", None) or ""
    owner = OwnerInfo(
        owner_name=body.owner_name,
        survey_number=body.survey_number,
        locality=body.locality,
        engineer_name=body.engineer_name,
        license_number=body.license_number,
        municipality=municipality,
    )

    pdf_bytes = generate_approval_pdf(layout, cfg, owner, layout_id)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="planforge-approval-{project_id}-layout-{layout_id}.pdf"'
            )
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
        import ezdxf  # noqa: F401
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

    from app.engine.cad_advanced import (
        draw_building_footprint,
        draw_compound_wall,
        draw_furniture,
        draw_open_terrace,
        draw_setback_zones,
        draw_structural_grid,
    )
    from app.engine.cad_elements import build_walls_from_rooms
    from app.engine.cad_primitives import (
        collect_openings,
        draw_dimension_chain,
        draw_door,
        draw_north_arrow,
        draw_staircase,
        draw_title_block,
        draw_ventilator,
        draw_wall_with_breaks,
        draw_window,
        metres_to_ftin,
    )

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6  # metres

    layer_defs = [
        ("PLOT-BOUNDARY",   colors.GREEN,   0.25),
        ("A-WALL-BRICK",    colors.RED,     0.50),
        ("A-WALL-INT",      colors.YELLOW,  0.35),
        ("A-DOOR",          colors.CYAN,    0.25),
        ("A-WINDOW",        colors.BLUE,    0.25),
        ("A-STAIR",         colors.WHITE,   0.25),
        ("A-VENTILATOR",    colors.MAGENTA, 0.18),
        ("A-TITLE",         colors.WHITE,   0.50),
        ("S-COLUMN",        colors.WHITE,   0.35),
        ("S-BEAM",          colors.WHITE,   0.35),
        ("S-GRID",          colors.GRAY,    0.18),
        ("DIM-LINE",        colors.GRAY,    0.18),
        ("TEXT",            colors.WHITE,   0.18),
        # Advanced CAD layers
        ("A-FOOTPRINT",     colors.WHITE,   0.70),
        ("A-COMPOUND-WALL", colors.GREEN,   0.35),
        ("A-TERRACE",       colors.CYAN,    0.18),
        ("A-FURNITURE",     colors.BLUE,    0.18),
        ("DIM-SETBACK",     colors.GRAY,    0.18),
    ]
    # Structural layers are frozen by default so architectural drawing stays clean
    structural_layers = {"S-COLUMN", "S-BEAM", "S-GRID"}

    for lname, color, lw in layer_defs:
        lyr = doc.layers.new(lname)
        lyr.color = color
        lyr.lineweight = int(lw * 100)
        if lname in structural_layers:
            lyr.freeze()

    # Register DASHED linetype (used by plot boundary and structural grid)
    if "DASHED" not in doc.linetypes:
        doc.linetypes.new("DASHED", dxfattribs={"description": "Dashed _ _ _"})

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

    ewt_m = 0.23    # external wall thickness (m)
    iwt_m = 0.115   # internal (half-brick) wall thickness

    global_min_x = global_min_y = float("inf")
    global_max_x = global_max_y = float("-inf")

    # Ground-floor building extents needed for post-loop setback callouts
    gf_bld_x = gf_bld_y = gf_bld_w = gf_bld_d = 0.0

    for floor_plan in floor_plans:
        z_offset = float(floor_plan.floor) * 3.0
        rooms = floor_plan.rooms
        if not rooms:
            continue

        bld_x = min(r.x for r in rooms)
        bld_y = min(r.y for r in rooms)
        bld_w = max(r.x + r.width for r in rooms) - bld_x
        bld_d = max(r.y + r.depth for r in rooms) - bld_y

        if floor_plan.floor == 0:
            gf_bld_x, gf_bld_y, gf_bld_w, gf_bld_d = bld_x, bld_y, bld_w, bld_d

        global_min_x = min(global_min_x, bld_x)
        global_min_y = min(global_min_y, bld_y)
        global_max_x = max(global_max_x, bld_x + bld_w)
        global_max_y = max(global_max_y, bld_y + bld_d)

        # 1. Collect all openings (doors, windows, ventilators)
        openings_map = collect_openings(rooms, ewt_m, iwt_m, bld_x, bld_y, bld_w, bld_d)

        # 2. Draw walls with clean gaps at openings
        walls = build_walls_from_rooms(rooms, ewt_m, iwt_m, bld_x, bld_y, bld_w, bld_d)
        for wall in walls:
            wall_key = (round(wall.x1, 2), round(wall.y1, 2),
                        round(wall.x2, 2), round(wall.y2, 2))
            lyr_name = "A-WALL-BRICK" if wall.thickness >= ewt_m else "A-WALL-INT"
            draw_wall_with_breaks(
                msp, wall, openings_map.get(wall_key, []), lyr_name, z_offset
            )

        # 3. Draw opening symbols in the gaps
        for wall_openings in openings_map.values():
            for op in wall_openings:
                if op.kind == "door":
                    draw_door(msp, op.cx, op.cy, op.width,
                              op.is_vertical_wall, swing_left=True,
                              layer="A-DOOR", z=z_offset)
                elif op.kind == "window":
                    draw_window(msp, op.cx, op.cy, op.width,
                                not op.is_vertical_wall, ewt_m,
                                layer="A-WINDOW", z=z_offset)
                elif op.kind == "ventilator":
                    draw_ventilator(msp, op.cx, op.cy,
                                    not op.is_vertical_wall,
                                    layer="A-VENTILATOR", z=z_offset)

        # 4. Staircase treads + cut line + UP arrow
        for room in rooms:
            if room.type == "staircase":
                draw_staircase(msp, room, layer="A-STAIR", z=z_offset)

        # 5. Room labels in feet-inches
        for room in rooms:
            cx = room.x + room.width / 2
            cy = room.y + room.depth / 2
            label = (f"{room.name}\\P"
                     f"{metres_to_ftin(room.width)} x {metres_to_ftin(room.depth)}")
            msp.add_mtext(
                label,
                dxfattribs={
                    "layer": "TEXT",
                    "char_height": 0.2,
                    "insert": (cx, cy, z_offset),
                    "attachment_point": 5,
                },
            )

        # 6. Columns
        half = 0.15
        seen: set = set()
        for col in floor_plan.columns:
            col_key = (round(col.x, 2), round(col.y, 2))
            if col_key in seen:
                continue
            seen.add(col_key)
            pts_col = [
                (col.x - half, col.y - half),
                (col.x + half, col.y - half),
                (col.x + half, col.y + half),
                (col.x - half, col.y + half),
            ]
            msp.add_lwpolyline(
                pts_col, close=True,
                dxfattribs={"layer": "S-COLUMN", "elevation": z_offset},
            )

        # 6a. Bold building outline (unary_union of room boxes)
        footprint = draw_building_footprint(msp, rooms, layer="A-FOOTPRINT", z=z_offset)

        # 6b. Structural grid (ground floor only)
        if floor_plan.floor == 0:
            draw_structural_grid(msp, rooms, bld_x, bld_y, bld_w, bld_d,
                                 layer="S-GRID", z=z_offset)

        # 6c. Furniture per room
        for room in rooms:
            draw_furniture(msp, room, layer="A-FURNITURE", z=z_offset)

        # 6d. Open terrace hatching (ground floor only)
        if floor_plan.floor == 0 and footprint is not None:
            from shapely.geometry import Polygon as _SPoly
            from shapely.geometry import box as _sbox
            plot_poly = (
                _SPoly([(float(x), float(y)) for x, y in cfg.plot_corners])
                if cfg.plot_shape == "quadrilateral" and cfg.plot_corners
                else _sbox(0, 0, cfg.plot_width, cfg.plot_length)
            )
            draw_open_terrace(msp, plot_poly, footprint, layer="A-TERRACE", z=z_offset)

        # 7. Feet-inches dimension chains
        xs = sorted({round(r.x, 3) for r in rooms} | {round(r.x + r.width, 3) for r in rooms})
        ys = sorted({round(r.y, 3) for r in rooms} | {round(r.y + r.depth, 3) for r in rooms})
        draw_dimension_chain(msp, xs, fixed_coord=bld_y, offset=-1.5,
                             is_horizontal=True, layer="DIM-LINE", z=z_offset)
        draw_dimension_chain(msp, ys, fixed_coord=bld_x + bld_w, offset=1.5,
                             is_horizontal=False, layer="DIM-LINE", z=z_offset)

    # ── North arrow (top-right, drawn once outside floor loop) ───────────────
    if global_max_x < float("inf"):
        north_dir = getattr(cfg, "road_side", "S") or "S"
        draw_north_arrow(msp, cx=global_max_x + 2.5, cy=global_max_y - 1.5,
                         north_dir=north_dir, size=0.8, layer="TEXT")

        # ── Setback dimension callouts (ground floor extents) ─────────────────
        draw_setback_zones(msp, cfg, gf_bld_x, gf_bld_y, gf_bld_w, gf_bld_d,
                           layer="DIM-SETBACK", z=0.0)

        # ── Compound boundary wall with gate ─────────────────────────────────
        draw_compound_wall(msp, cfg, layer="A-COMPOUND-WALL", z=0.0)

        # ── Title block (below the drawing) ───────────────────────────────────
        gf_sqft = sum(r.area for r in layout.ground_floor.rooms) * 10.764
        ff_sqft = sum(r.area for r in layout.first_floor.rooms) * 10.764
        draw_title_block(
            msp,
            project_name=project_name,
            layout_id=layout.id,
            gf_area_sqft=gf_sqft,
            ff_area_sqft=ff_sqft,
            plot_w=cfg.plot_width,
            plot_l=cfg.plot_length,
            insert_x=global_min_x,
            insert_y=global_min_y - 5.5,
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
    city: str = "Generic",
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
    boq = engine.calculate(layout, cfg, project_name=project.name, city=city)

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
        import openpyxl  # noqa: F401
    except ImportError:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED,
                            detail="openpyxl not installed. Run: uv add openpyxl")

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "BOQ"

    # Title row 1: project + layout
    ws.merge_cells("A1:F1")
    ws["A1"] = f"Bill of Quantities — {boq.project_name} / Layout {boq.layout_id}"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A1"].alignment = Alignment(horizontal="center")

    # Title row 2: city / rates note
    ws.merge_cells("A2:F2")
    ws["A2"] = boq.rates_note
    ws["A2"].font = Font(italic=True, size=10, color="555555")
    ws["A2"].alignment = Alignment(horizontal="center")

    # Column headers
    headers = ["S.No", "Item Description", "Quantity", "Unit", "Rate (₹)", "Amount (₹)"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1E3A5F")
        cell.alignment = Alignment(horizontal="center")

    # Data rows
    for row_idx, item in enumerate(boq.line_items, start=5):
        ws.cell(row=row_idx, column=1, value=item.item)
        ws.cell(row=row_idx, column=2, value=item.description)
        ws.cell(row=row_idx, column=3, value=item.quantity)
        ws.cell(row=row_idx, column=4, value=item.unit)
        ws.cell(row=row_idx, column=5, value=round(item.rate, 2) if item.rate else "")
        ws.cell(row=row_idx, column=6, value=round(item.amount) if item.amount else "")

    # Total row
    total_row = len(boq.line_items) + 6
    ws.cell(row=total_row, column=2, value="TOTAL ESTIMATED COST")
    ws.cell(row=total_row, column=2).font = Font(bold=True)
    ws.cell(row=total_row, column=6, value=round(boq.total_cost))
    ws.cell(row=total_row, column=6).font = Font(bold=True)

    # City comparison row
    if boq.city != "Generic" and boq.cost_difference is not None:
        diff = boq.cost_difference
        diff_label = (f"vs Generic: +₹{diff:,.0f} more" if diff > 0
                      else f"vs Generic: ₹{abs(diff):,.0f} less")
        compare_row = total_row + 1
        ws.cell(row=compare_row, column=2, value=diff_label)
        ws.cell(row=compare_row, column=2).font = Font(
            italic=True, color="CC0000" if diff > 0 else "007700"
        )

    # Auto-width columns
    for col in ws.columns:
        max_len = max((len(str(cell.value or "")) for cell in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = max(max_len + 2, 12)

    # Footer note
    note_row = len(boq.line_items) + 9
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
