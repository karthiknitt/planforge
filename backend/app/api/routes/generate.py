from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.revisions import save_auto_revision
from app.db import get_db
from app.dependencies.auth import get_current_user_id
from app.engine.generator import generate_from_request
from app.schemas.layout import GenerateResponse, LayoutOut
from app.schemas.project import GenerateRequest
from app.services import layout_store
from app.services.access import get_accessible_project

router = APIRouter()


@router.post("/generate", response_model=list[LayoutOut])
async def generate_preview(
    req: GenerateRequest,
    user_id: str = Depends(get_current_user_id),
) -> list[LayoutOut]:
    """Stateless wizard preview: solve straight from a GenerateRequest.

    Nothing is persisted — no project row, no stored layout. The wizard's
    "Site & Style" step (Task 24) posts here once the flow is wired; until
    then the endpoint is the contract Task 25 produces.
    """
    layouts = generate_from_request(req)
    return [layout_store.layout_out_from_engine(lay) for lay in layouts]


@router.get("/projects/{project_id}/generate", response_model=GenerateResponse)
async def generate_layouts(
    project_id: str,
    refresh: bool = False,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> GenerateResponse:
    """Return the project's layouts.

    Layouts are solved once and persisted; subsequent calls read the store so
    the viewer, share view and exports all see the same geometry. Pass
    ?refresh=true to explicitly re-run the solver (a revision snapshot of the
    current state is taken first).
    """
    project = await get_accessible_project(project_id, user_id, db)

    if refresh:
        # Fire-and-forget snapshot: failure must not block regeneration
        try:
            await save_auto_revision(
                db, project, label_prefix="Auto-save before regeneration"
            )
        except Exception:
            pass
        try:
            stored = await layout_store.regenerate_and_store(project, db)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        try:
            stored = await layout_store.get_or_generate_layouts(project, db)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return layout_store.to_generate_response(project, stored)


@router.get("/projects/{project_id}/layouts", response_model=GenerateResponse)
async def read_layouts(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> GenerateResponse:
    """Read stored layouts. Never solves — generation is an explicit job
    (POST /projects/{id}/generate-jobs). Empty list means nothing generated yet."""
    project = await get_accessible_project(project_id, user_id, db)
    stored = await layout_store.get_stored_layouts(project.id, db)
    return layout_store.to_generate_response(project, stored)
