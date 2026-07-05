from app.models.project import Project
from app.models.user import User
from app.services.plans import TIER_ORDER, tier_at_least


def test_tier_order_is_free_basic_pro_firm():
    assert TIER_ORDER == ("free", "basic", "pro", "firm")


def test_firm_is_at_least_pro():
    assert tier_at_least("firm", "pro")


def test_firm_is_at_least_basic():
    assert tier_at_least("firm", "basic")


def test_basic_is_not_pro():
    assert not tier_at_least("basic", "pro")


def test_unknown_tier_ranks_as_free():
    assert not tier_at_least("enterprise", "basic")
    assert tier_at_least("enterprise", "free")


# ── Regression tests: firm tier passes gate checks ────────────────────────────


async def _seed_user(session_factory, user_id: str, plan_tier: str) -> None:
    """Seed a user with a specific plan tier."""
    async with session_factory() as session:
        session.add(User(id=user_id, plan_tier=plan_tier))
        await session.commit()


async def _seed_project(session_factory, user_id: str) -> str:
    """Seed a project for the given user. Returns project id."""
    async with session_factory() as session:
        project = Project(
            id="test-proj-1",
            user_id=user_id,
            name="Test Project",
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
        )
        session.add(project)
        await session.commit()
        return project.id


async def test_firm_user_passes_edit_gate(client_db):
    """Firm user hitting the edit PATCH gets past the tier gate.

    (404 for a nonexistent layout is fine — 403 "Pro plan required" is the failure)
    """
    client, SessionLocal = client_db
    await _seed_user(SessionLocal, "firm-user", "firm")
    project_id = await _seed_project(SessionLocal, "firm-user")
    resp = await client.patch(
        f"/api/projects/{project_id}/layouts/nope",
        json={
            "rooms": [
                {
                    "id": "r1",
                    "type": "bedroom",
                    "name": "B",
                    "x": 1,
                    "y": 1,
                    "width": 3,
                    "height": 3,
                    "floor": "gf",
                }
            ]
        },
        headers={"X-Test-User-Id": "firm-user"},
    )
    assert resp.status_code != 403
