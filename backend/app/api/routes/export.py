from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.engine.generator import generate
from app.engine.models import PlotConfig
from app.engine.pdf import render_pdf
from app.models.project import Project

router = APIRouter()


def _to_float(v) -> float:
    return float(v) if isinstance(v, Decimal) else v


def _user_id(x_user_id: str = Header(..., alias="X-User-Id")) -> str:
    return x_user_id


@router.get("/projects/{project_id}/export/pdf")
async def export_pdf(
    project_id: str,
    layout_id: str = "A",
    user_id: str = Depends(_user_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    cfg = PlotConfig(
        plot_length=_to_float(project.plot_length),
        plot_width=_to_float(project.plot_width),
        setback_front=_to_float(project.setback_front),
        setback_rear=_to_float(project.setback_rear),
        setback_left=_to_float(project.setback_left),
        setback_right=_to_float(project.setback_right),
        bhk=project.bhk,
        toilets=project.toilets,
        parking=project.parking,
    )

    layouts = generate(cfg)
    layout = next((lay for lay in layouts if lay.id == layout_id), None)
    if layout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Layout {layout_id!r} not found")

    pdf_bytes = render_pdf(project.name, layout, cfg, project.bhk)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="planforge-{project_id}-layout-{layout_id}.pdf"'
        },
    )
