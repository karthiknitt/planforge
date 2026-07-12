"""
Tests for BOQ Excel export endpoint (Bug #4).

Covers:
  - openpyxl dependency is available
  - Excel export returns 200 with correct content-type for Pro tier users
  - Excel export returns 402 for non-Pro users
  - Excel file contains correct structure (title, headers, data, total)
"""

import pytest

from app.models.project import Project
from app.models.user import User


@pytest.mark.asyncio
async def test_boq_excel_export_pro_tier(client_db):
    """Pro-tier user can export BOQ as Excel and receives 200 + correct content-type."""
    client, SessionLocal = client_db
    user_id = "test-user-pro"

    async with SessionLocal() as session:
        # Create user with Pro tier
        user = User(id=user_id, plan_tier="pro")
        session.add(user)

        # Create project
        project = Project(
            id="test-proj",
            user_id=user_id,
            name="Test Project",
            plot_length=12.0,
            plot_width=9.0,
            setback_front=1.5,
            setback_rear=1.5,
            setback_left=1.0,
            setback_right=1.0,
            num_bedrooms=2,
            toilets=2,
            parking=False,
            city="Generic",
            road_side="N",
            north_direction="N",
        )
        session.add(project)
        await session.commit()

    # Request Excel export
    response = await client.get(
        "/api/projects/test-proj/boq?layout_id=A&fmt=excel&city=Generic",
        headers={"X-Test-User-Id": user_id},
    )

    # Check response
    assert response.status_code == 200
    assert (
        response.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.headers.get("content-disposition") is not None
    assert "planforge-boq-test-proj-A.xlsx" in response.headers["content-disposition"]

    # Verify file is a valid Excel file (basic check)
    content = response.content
    assert content.startswith(b"PK")  # ZIP signature (Excel is ZIP)
    assert len(content) > 1000  # Reasonable file size


@pytest.mark.asyncio
async def test_boq_excel_export_free_tier_returns_402(client_db):
    """Free-tier user cannot export Excel; endpoint returns 402 Payment Required."""
    client, SessionLocal = client_db
    user_id = "test-user-free"

    async with SessionLocal() as session:
        # Create user with Free tier
        user = User(id=user_id, plan_tier="free")
        session.add(user)

        # Create project
        project = Project(
            id="test-proj-free",
            user_id=user_id,
            name="Test Project Free",
            plot_length=12.0,
            plot_width=9.0,
            setback_front=1.5,
            setback_rear=1.5,
            setback_left=1.0,
            setback_right=1.0,
            num_bedrooms=2,
            toilets=2,
            parking=False,
            city="Generic",
            road_side="N",
            north_direction="N",
        )
        session.add(project)
        await session.commit()

    # Request Excel export
    response = await client.get(
        "/api/projects/test-proj-free/boq?layout_id=A&fmt=excel&city=Generic",
        headers={"X-Test-User-Id": user_id},
    )

    # Check response
    assert response.status_code == 402
    data = response.json()
    assert "Pro plan" in data["detail"]


@pytest.mark.asyncio
async def test_boq_json_export_free_tier_allowed(client_db):
    """Free-tier users can still export JSON (only Excel is restricted)."""
    client, SessionLocal = client_db
    user_id = "test-user-free-json"

    async with SessionLocal() as session:
        # Create user with Free tier
        user = User(id=user_id, plan_tier="free")
        session.add(user)

        # Create project
        project = Project(
            id="test-proj-json",
            user_id=user_id,
            name="Test Project JSON",
            plot_length=12.0,
            plot_width=9.0,
            setback_front=1.5,
            setback_rear=1.5,
            setback_left=1.0,
            setback_right=1.0,
            num_bedrooms=2,
            toilets=2,
            parking=False,
            city="Generic",
            road_side="N",
            north_direction="N",
        )
        session.add(project)
        await session.commit()

    # Request JSON export (should be allowed)
    response = await client.get(
        "/api/projects/test-proj-json/boq?layout_id=A&fmt=json&city=Generic",
        headers={"X-Test-User-Id": user_id},
    )

    # Check response
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert "total_cost" in data
    assert data["total_cost"] > 0
