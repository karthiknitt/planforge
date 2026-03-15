from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.project import Project
from app.models.team import Team, TeamMember
from app.schemas.project import ProjectRead

router = APIRouter()


def _get_user_id(x_user_id: str = Header(..., alias="X-User-Id")) -> str:
    return x_user_id


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class TeamCreate(BaseModel):
    name: str


class TeamRead(BaseModel):
    id: int
    name: str
    owner_id: str
    plan_tier: str
    plan_expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TeamMemberRead(BaseModel):
    id: int
    team_id: int
    user_id: str
    role: str
    invited_email: str | None
    joined_at: datetime

    model_config = {"from_attributes": True}


class InviteMemberRequest(BaseModel):
    email: str
    role: str = "member"  # "admin" | "member"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_team_or_404(team_id: int, db: AsyncSession) -> Team:
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team


async def _get_membership(team_id: int, user_id: str, db: AsyncSession) -> TeamMember | None:
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def _require_admin(team_id: int, user_id: str, db: AsyncSession) -> None:
    member = await _get_membership(team_id, user_id, db)
    if not member or member.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Team admin access required",
        )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/teams", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
async def create_team(
    body: TeamCreate,
    user_id: str = Depends(_get_user_id),
    db: AsyncSession = Depends(get_db),
) -> Team:
    # One team per user (as owner) — soft guard
    existing = await db.execute(select(Team).where(Team.owner_id == user_id))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already own a team. Transfer ownership or delete it first.",
        )

    team = Team(name=body.name, owner_id=user_id)
    db.add(team)
    await db.flush()  # get team.id before inserting member

    admin_member = TeamMember(team_id=team.id, user_id=user_id, role="admin")
    db.add(admin_member)
    await db.commit()
    await db.refresh(team)
    return team


@router.get("/teams/mine", response_model=TeamRead | None)
async def get_my_team(
    user_id: str = Depends(_get_user_id),
    db: AsyncSession = Depends(get_db),
) -> Team | None:
    """Return the team the current user belongs to (as any role)."""
    result = await db.execute(
        select(Team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user_id)
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.get("/teams/{team_id}/members", response_model=list[TeamMemberRead])
async def list_members(
    team_id: int,
    user_id: str = Depends(_get_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[TeamMember]:
    await _get_team_or_404(team_id, db)
    membership = await _get_membership(team_id, user_id, db)
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")

    result = await db.execute(
        select(TeamMember).where(TeamMember.team_id == team_id)
    )
    return list(result.scalars().all())


@router.post(
    "/teams/{team_id}/members",
    response_model=TeamMemberRead,
    status_code=status.HTTP_201_CREATED,
)
async def invite_member(
    team_id: int,
    body: InviteMemberRequest,
    user_id: str = Depends(_get_user_id),
    db: AsyncSession = Depends(get_db),
) -> TeamMember:
    """Invite a member by email. No email is sent — share the invite link manually."""
    await _get_team_or_404(team_id, db)
    await _require_admin(team_id, user_id, db)

    if body.role not in ("admin", "member"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'member'")

    # Prevent duplicate invites for the same email
    dup = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.invited_email == body.email,
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="This email has already been invited")

    member = TeamMember(
        team_id=team_id,
        user_id="",          # empty until the invitee logs in and claims the invite
        role=body.role,
        invited_email=body.email,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


@router.delete("/teams/{team_id}/members/{target_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    team_id: int,
    target_user_id: str,
    user_id: str = Depends(_get_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_team_or_404(team_id, db)
    await _require_admin(team_id, user_id, db)

    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == target_user_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    await db.delete(member)
    await db.commit()


@router.get("/teams/{team_id}/projects", response_model=list[ProjectRead])
async def list_team_projects(
    team_id: int,
    user_id: str = Depends(_get_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[Project]:
    await _get_team_or_404(team_id, db)
    membership = await _get_membership(team_id, user_id, db)
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")

    result = await db.execute(
        select(Project)
        .where(Project.team_id == team_id)
        .order_by(Project.created_at.desc())
    )
    return list(result.scalars().all())
