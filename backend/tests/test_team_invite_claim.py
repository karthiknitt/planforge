"""Regression tests for the team-invite claim flow.

`invite_member` creates a `TeamMember(user_id="", invited_email=<email>)` row
but nothing ever converted it into real membership. `POST /api/teams/claim`
closes that gap by matching the caller's *trusted* email — taken from the
`email` claim on the signed internal auth token (never a client-supplied
request body field) — against pending invite rows, case-insensitively.
"""

from app.models.team import Team, TeamMember

OWNER = "owner-user-1"
INVITEE = "invitee-user-1"
OUTSIDER = "outsider-user-1"
INVITED_EMAIL = "Invitee@Example.com"


async def _seed_team_with_invite(
    session_factory, invited_email: str = INVITED_EMAIL
) -> int:
    async with session_factory() as session:
        team = Team(name="Test Firm", owner_id=OWNER)
        session.add(team)
        await session.flush()
        session.add_all(
            [
                TeamMember(team_id=team.id, user_id=OWNER, role="admin"),
                TeamMember(
                    team_id=team.id,
                    user_id="",
                    role="member",
                    invited_email=invited_email,
                ),
            ]
        )
        await session.commit()
        return team.id


async def _seed_team_project(session_factory, team_id: int) -> str:
    from app.models.project import Project

    async with session_factory() as session:
        project = Project(
            id=f"team-proj-{team_id}",
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
            team_id=team_id,
        )
        session.add(project)
        await session.commit()
        return project.id


class TestClaimInvite:
    async def test_claim_grants_access_to_team_project(self, client_db):
        client, sf = client_db
        team_id = await _seed_team_with_invite(sf)
        project_id = await _seed_team_project(sf, team_id)

        # Case-insensitively different email in the token than what was
        # invited — claim must still match.
        claim_res = await client.post(
            "/api/teams/claim",
            headers={
                "X-Test-User-Id": INVITEE,
                "X-Test-User-Email": "invitee@example.com",
            },
        )
        assert claim_res.status_code == 200, claim_res.text
        assert claim_res.json() == {"claimed": 1}

        revisions_res = await client.get(
            f"/api/projects/{project_id}/revisions",
            headers={"X-Test-User-Id": INVITEE},
        )
        assert revisions_res.status_code == 200, revisions_res.text

    async def test_claim_with_no_matching_invite_is_a_noop(self, client_db):
        client, sf = client_db
        await _seed_team_with_invite(sf)

        res = await client.post(
            "/api/teams/claim",
            headers={
                "X-Test-User-Id": "nobody-invited",
                "X-Test-User-Email": "nobody@example.com",
            },
        )
        assert res.status_code == 200, res.text
        assert res.json() == {"claimed": 0}

    async def test_claim_without_email_is_400(self, client_db):
        client, _sf = client_db

        res = await client.post(
            "/api/teams/claim",
            headers={"X-Test-User-Id": INVITEE},
        )
        assert res.status_code == 400, res.text

    async def test_claim_twice_is_idempotent_no_duplicate_rows(self, client_db):
        client, sf = client_db
        team_id = await _seed_team_with_invite(sf)

        headers = {
            "X-Test-User-Id": INVITEE,
            "X-Test-User-Email": INVITED_EMAIL,
        }
        first = await client.post("/api/teams/claim", headers=headers)
        assert first.status_code == 200
        assert first.json() == {"claimed": 1}

        second = await client.post("/api/teams/claim", headers=headers)
        assert second.status_code == 200
        assert second.json() == {"claimed": 0}

        from sqlalchemy import select

        async with sf() as session:
            result = await session.execute(
                select(TeamMember).where(
                    TeamMember.team_id == team_id,
                    TeamMember.user_id == INVITEE,
                )
            )
            rows = result.scalars().all()
            assert len(rows) == 1

    async def test_empty_user_id_row_grants_no_access(self, client_db):
        client, sf = client_db
        team_id = await _seed_team_with_invite(sf)
        project_id = await _seed_team_project(sf, team_id)

        # Nobody has claimed the invite — the row is still user_id="".
        # No caller, however they authenticate, should be granted access
        # via that row.
        res = await client.get(
            f"/api/projects/{project_id}/revisions",
            headers={"X-Test-User-Id": ""},
        )
        assert res.status_code in (401, 404, 422)

        res_members = await client.get(
            f"/api/teams/{team_id}/members",
            headers={"X-Test-User-Id": OUTSIDER},
        )
        assert res_members.status_code == 403
