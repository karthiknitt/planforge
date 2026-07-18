"""Regression tests: team-project access parity + plan-expiry enforcement.

Bug 1: projects.py granted team members access, but rooms/export/generate/
share/revisions filtered on user_id == owner only — team members could list
team projects yet not generate/export/share/edit them.

Bug 2: plan_expires_at was written by payments/verify but never read — an
expired Pro subscription kept Pro features forever.
"""

from datetime import datetime, timedelta, timezone


from app.models.project import Project
from app.models.team import Team, TeamMember
from app.models.user import User
from app.services.plans import get_effective_plan_tier

OWNER = "owner-user-1"
MEMBER = "member-user-1"
OUTSIDER = "outsider-user-1"


async def _seed_team_project(session_factory) -> str:
    """Create a team (OWNER admin, MEMBER member) and a team project. Returns project id."""
    async with session_factory() as session:
        team = Team(name="Test Firm", owner_id=OWNER)
        session.add(team)
        await session.flush()
        session.add_all(
            [
                TeamMember(team_id=team.id, user_id=OWNER, role="admin"),
                TeamMember(team_id=team.id, user_id=MEMBER, role="member"),
            ]
        )
        project = Project(
            id="team-proj-1",
            user_id=OWNER,
            name="Team Project",
            plot_length=15.0,
            plot_width=10.0,
            setback_front=1.5,
            setback_rear=1.0,
            setback_left=1.0,
            setback_right=1.0,
            road_side="S",
            north_direction="N",
            num_bedrooms=2,
            toilets=2,
            parking=False,
            team_id=team.id,
        )
        session.add(project)
        await session.commit()
        return project.id


class TestTeamAccessParity:
    async def test_team_member_can_list_revisions(self, client_db):
        client, sf = client_db
        pid = await _seed_team_project(sf)
        res = await client.get(
            f"/api/projects/{pid}/revisions", headers={"X-Test-User-Id": MEMBER}
        )
        assert res.status_code == 200, res.text

    async def test_team_member_can_create_share_link(self, client_db):
        client, sf = client_db
        pid = await _seed_team_project(sf)
        res = await client.post(
            f"/api/projects/{pid}/share", headers={"X-Test-User-Id": MEMBER}
        )
        assert res.status_code == 200, res.text

    async def test_outsider_cannot_list_revisions(self, client_db):
        client, sf = client_db
        pid = await _seed_team_project(sf)
        res = await client.get(
            f"/api/projects/{pid}/revisions", headers={"X-Test-User-Id": OUTSIDER}
        )
        assert res.status_code == 404

    async def test_outsider_cannot_create_share_link(self, client_db):
        client, sf = client_db
        pid = await _seed_team_project(sf)
        res = await client.post(
            f"/api/projects/{pid}/share", headers={"X-Test-User-Id": OUTSIDER}
        )
        assert res.status_code == 404


class TestPlanExpiry:
    async def test_expired_pro_is_effectively_free(self, client_db):
        _, sf = client_db
        async with sf() as session:
            session.add(
                User(
                    id="expired-pro",
                    plan_tier="pro",
                    plan_expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                )
            )
            await session.commit()
            assert await get_effective_plan_tier("expired-pro", session) == "free"

    async def test_active_pro_stays_pro(self, client_db):
        _, sf = client_db
        async with sf() as session:
            session.add(
                User(
                    id="active-pro",
                    plan_tier="pro",
                    plan_expires_at=datetime.now(timezone.utc) + timedelta(days=10),
                )
            )
            await session.commit()
            assert await get_effective_plan_tier("active-pro", session) == "pro"

    async def test_null_expiry_keeps_tier(self, client_db):
        _, sf = client_db
        async with sf() as session:
            session.add(User(id="legacy-basic", plan_tier="basic"))
            await session.commit()
            assert await get_effective_plan_tier("legacy-basic", session) == "basic"

    async def test_unknown_user_is_free(self, client_db):
        _, sf = client_db
        async with sf() as session:
            assert await get_effective_plan_tier("nobody", session) == "free"

    async def test_expired_pro_blocked_from_pro_endpoint(self, client_db):
        client, sf = client_db
        pid = await _seed_team_project(sf)
        async with sf() as session:
            session.add(
                User(
                    id=OWNER,
                    plan_tier="pro",
                    plan_expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                )
            )
            await session.commit()
        res = await client.get(
            f"/api/projects/{pid}/rooms", headers={"X-Test-User-Id": OWNER}
        )
        assert res.status_code == 403


class TestTeamCreationTierGate:
    """Regression: POST /api/teams had no plan-tier check — any free user
    could create a 'firm' and use the multi-seat collaboration feature
    (priced as the Firm plan) via direct API call."""

    async def test_free_user_cannot_create_team(self, client_db):
        client, sf = client_db
        async with sf() as session:
            session.add(User(id="free-user-1", plan_tier="free"))
            await session.commit()
        res = await client.post(
            "/api/teams",
            json={"name": "Freeloaders LLP"},
            headers={"X-Test-User-Id": "free-user-1"},
        )
        assert res.status_code == 403, res.text
        assert "firm" in res.json()["detail"].lower()

    async def test_firm_user_can_create_team(self, client_db):
        client, sf = client_db
        async with sf() as session:
            session.add(User(id="firm-user-1", plan_tier="firm"))
            await session.commit()
        res = await client.post(
            "/api/teams",
            json={"name": "Real Firm"},
            headers={"X-Test-User-Id": "firm-user-1"},
        )
        assert res.status_code == 201, res.text
