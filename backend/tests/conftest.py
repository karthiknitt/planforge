"""Shared pytest fixtures for API integration tests."""

import os

os.environ.setdefault("INTERNAL_AUTH_SECRET", "test-secret-for-ci-0123456789abcdefgh")

import pytest
from fastapi import Header
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base, get_db
from app.dependencies.auth import get_current_user_email, get_current_user_id
from app.main import app

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

# Files auto-marked `slow` below (2026-08-16 per-file isolation run, see
# .superpowers/sdd/2026-08-15-solver-capability-uplift/task-9A-report.md).
# Threshold picked from a natural cliff in the measured wall-clock data: every
# file in this set ran >=24s in isolation; every file NOT in this set ran <=6s.
# There is no ambiguous middle — files here run the real CP-SAT solve (or a
# generation pipeline downstream of one: DXF/PDF/BOQ/structural-sheet
# rendering off a solved layout); files outside it work off fixtures/mocks.
# `-m "not slow"` (the dev fast path) skips these; the full suite still runs
# them by default (no marker filter in [tool.pytest.ini_options]).
_SLOW_TEST_FILES = frozenset(
    {
        "test_engine.py",
        "test_api_e2e.py",
        "test_render_endpoint.py",
        "test_layout_persistence.py",
        "test_solver.py",
        "test_ff_space_optimization.py",
        "test_section_geometry.py",
        "test_revision_history.py",
        "test_boq_city_rates.py",
        "test_l_shaped_compliance_area.py",
        "test_solver_shapes.py",
        "test_share_token.py",
        "test_approval_section_pages.py",
        "test_boq_excel_export.py",
        "test_pdf_section_pages.py",
        "test_render_jobs.py",
        "test_quad_plots.py",
        "test_stair_wet_separation.py",
        "test_undo_persistence.py",
        "test_quality_endpoint.py",
        "test_engine_math_fixes.py",
        "test_section_render.py",
        "test_solver_envelope.py",
        "test_l_shaped.py",
        "test_structural_loop.py",
        "test_layouts_read_endpoint.py",
        "test_agent_no_solve.py",
        "test_structural_drawing_set.py",
        "test_solver_grid_alignment.py",
        "test_sheet_foundation.py",
        "test_sheet_framing.py",
        "test_column_consistency.py",
        "test_dxf_dimstyle.py",
        "test_sheet_slab_stair.py",
        "test_l_shaped_plots.py",
        "test_generation_jobs.py",
        "test_dxf_wall_hatch.py",
        "test_dxf_doc_setup.py",
        "test_generate_jobs_endpoint.py",
        "test_dxf_floor_drawing_projection.py",
        "test_dxf_blocks.py",
        "test_structural_revisions.py",
    }
)


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Auto-apply the `slow` marker by file, so no test body has to change."""
    slow_marker = pytest.mark.slow
    for item in items:
        if item.path.name in _SLOW_TEST_FILES:
            item.add_marker(slow_marker)


def _test_user_id_override(
    x_test_user_id: str = Header(..., alias="X-Test-User-Id"),
) -> str:
    return x_test_user_id


def _test_user_email_override(
    x_test_user_email: str | None = Header(None, alias="X-Test-User-Email"),
) -> str | None:
    return x_test_user_email


@pytest.fixture
async def client():
    """AsyncClient wired to an isolated in-memory SQLite database."""
    engine = create_async_engine(TEST_DB_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db() -> AsyncSession:
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = _test_user_id_override
    app.dependency_overrides[get_current_user_email] = _test_user_email_override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def client_real_auth():
    """AsyncClient wired to an isolated DB, WITHOUT overriding get_current_user_id —
    requests go through the real X-Internal-Auth JWT verification path, unlike
    the `client` fixture above (which every other test uses for convenience)."""
    engine = create_async_engine(TEST_DB_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db() -> AsyncSession:
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def client_db():
    """Like `client`, but also exposes the session factory so tests can seed
    rows (teams, users, projects) directly."""
    engine = create_async_engine(TEST_DB_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db() -> AsyncSession:
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = _test_user_id_override
    app.dependency_overrides[get_current_user_email] = _test_user_email_override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c, SessionLocal

    app.dependency_overrides.clear()
    await engine.dispose()
