from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies.auth import get_current_user_id
from app.schemas.job import JobOut
from app.services import jobs
from app.services.access import get_accessible_project

router = APIRouter()


@router.get("/projects/{project_id}/jobs/{job_id}", response_model=JobOut)
async def read_job(
    project_id: str,
    job_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> JobOut:
    project = await get_accessible_project(project_id, user_id, db)
    job = await jobs.get_job(db, project.id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobOut.model_validate(job)
