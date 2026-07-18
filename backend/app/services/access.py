"""Project access control — owner OR member of the project's team.

Previously only projects.py honoured team membership; every other router
(rooms, export, generate, share, revisions) was owner-only, so firm-plan
members could list team projects but not work on them.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.team import TeamMember


async def get_accessible_project(
    project_id: str, user_id: str, db: AsyncSession
) -> Project:
    """Return the project if `user_id` may access it; raise 404 otherwise.

    404 (not 403) for inaccessible projects so outsiders cannot probe
    which project IDs exist.
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    if project.user_id == user_id:
        return project
    if project.team_id is not None:
        member = await db.execute(
            select(TeamMember.id).where(
                TeamMember.team_id == project.team_id,
                TeamMember.user_id == user_id,
                TeamMember.user_id != "",
            )
        )
        if member.scalar_one_or_none() is not None:
            return project
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
