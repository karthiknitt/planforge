"""Closed-loop structural design (Stage 2.4).

structapi violations re-constrain the solver (span caps), the re-solve is
drift-minimised against the approved plan, the loop caps at 3 iterations,
and the stored layout is never overwritten — adjusted geometry lands in
StructuralDesign.final_geometry with a deterministic changelog.
"""

import asyncio

import httpx
import pytest

from app.config.settings import settings
from app.engine.models import Column, ComplianceResult, FloorPlan, Layout, Room
from app.models.layout import StoredLayout
from app.models.structural import StructuralDesign
from app.services import structagent_client, structural_loop

HDRS = {"X-Test-User-Id": "loop-owner"}

PROJECT_BODY = {
    "name": "Loop Test",
    "plot_length": 15.0,
    "plot_width": 10.0,
    "setback_front": 1.5,
    "setback_rear": 1.0,
    "setback_left": 1.0,
    "setback_right": 1.0,
    "road_side": "S",
    "north_direction": "N",
    "num_bedrooms": 2,
    "toilets": 2,
    "parking": False,
}

GRID_COLUMNS = [{"x": x, "y": y} for x in (0.0, 4.0, 8.0) for y in (0.0, 4.5)]
IRREGULAR_COLUMNS = [{"x": x, "y": y} for x in (0.0, 0.9) for y in (0.0, 4.0)]

ROOM_V1 = {
    "id": "living_0",
    "name": "Living Room",
    "type": "living",
    "x": 1.0,
    "y": 1.0,
    "width": 5.0,
    "depth": 4.0,
    "area": 20.0,
}

GEO_V1 = {
    "id": "A",
    "name": "Layout A",
    "ground_floor": {"floor": 0, "rooms": [ROOM_V1], "columns": GRID_COLUMNS},
    "first_floor": {"floor": 1, "rooms": [], "columns": []},
}

OK_ENVELOPE = {
    "api_version": "1",
    "ok": True,
    "checks": [{"name": "all pass", "ok": True}],
    "data": {"quantities": {}, "violations": []},
    "artifacts": [],
    "disclaimer": "verify against official BIS copies",
}

SPAN_VIOLATION = {
    "member_type": "beam",
    "axis": "x",
    "grid_ref": "beam line y=0, span 0",
    "span_m": 5.0,
    "check": "deflection L/d (cl 23.2.1)",
    "actual": 32.0,
    "limit": 26.0,
    "unit": "ratio",
    "remedy_hint": "reduce_span",
}

FAIL_ENVELOPE = {
    **OK_ENVELOPE,
    "ok": False,
    "checks": [{"name": "deflection L/d (cl 23.2.1)", "ok": False}],
    "data": {"quantities": {}, "violations": [SPAN_VIOLATION]},
}


def _adjusted_layout() -> Layout:
    return Layout(
        id="A",
        name="Layout A",
        ground_floor=FloorPlan(
            floor=0,
            floor_type="ground",
            rooms=[
                Room(
                    id="living_0",
                    name="Living Room",
                    type="living",
                    x=1.0,
                    y=1.0,
                    width=4.0,
                    depth=4.0,
                )
            ],
            columns=[Column(x=c["x"], y=c["y"]) for c in GRID_COLUMNS],
        ),
        first_floor=FloorPlan(floor=1, floor_type="first", rooms=[]),
        compliance=ComplianceResult(passed=True),
    )


async def _setup(client, SessionLocal, geometry=GEO_V1) -> str:
    res = await client.post("/api/projects", json=PROJECT_BODY, headers=HDRS)
    assert res.status_code == 201, res.text
    pid = res.json()["id"]
    async with SessionLocal() as s:
        s.add(
            StoredLayout(
                project_id=pid, layout_key="A", source="solver", geometry=geometry
            )
        )
        await s.commit()
    approve = await client.post(
        f"/api/projects/{pid}/structural/approve",
        json={"layout_id": "A"},
        headers=HDRS,
    )
    assert approve.status_code == 200, approve.text
    return pid


def _configure(monkeypatch, responses: list[dict]):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        idx = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        return httpx.Response(200, json=responses[idx])

    monkeypatch.setattr(settings, "structural_api_url", "http://sapi.test")
    monkeypatch.setattr(settings, "structural_api_key", "k1")
    monkeypatch.setattr(
        structagent_client, "_transport_for_tests", httpx.MockTransport(handler)
    )
    return calls


# ── unit: remedy math + changelog diff ──────────────────────────────────────


def test_cap_from_violation_reduce_span_uses_limit_ratio():
    cap = structural_loop.cap_from_violation(SPAN_VIOLATION)
    assert cap == round(5.0 * (26.0 / 32.0), 3)


def test_cap_from_violation_add_grid_line_halves_bay():
    v = {**SPAN_VIOLATION, "remedy_hint": "add_grid_line"}
    assert structural_loop.cap_from_violation(v) == round(5.0 * 0.55, 3)


def test_cap_from_violation_without_span_is_none():
    assert structural_loop.cap_from_violation({"remedy_hint": "reduce_span"}) is None


def test_diff_rooms_reports_resize_move_add_remove():
    before = {
        "ground_floor": {
            "rooms": [
                {**ROOM_V1},
                {**ROOM_V1, "id": "k", "name": "Kitchen", "x": 7.0},
            ]
        },
        "first_floor": {"rooms": []},
    }
    after = {
        "ground_floor": {
            "rooms": [
                {**ROOM_V1, "width": 4.0},
                {**ROOM_V1, "id": "t", "name": "Toilet"},
            ]
        },
        "first_floor": {"rooms": []},
    }
    entries = structural_loop.diff_rooms(before, after)
    joined = "\n".join(entries)
    assert "Living Room resized 5.0×4.0 m → 4.0×4.0 m" in joined
    assert "Kitchen removed" in joined
    assert "Toilet added" in joined


# ── endpoint loop behaviour ─────────────────────────────────────────────────


async def test_loop_converges_and_records_changelog(client_db, monkeypatch):
    client, SessionLocal = client_db
    pid = await _setup(client, SessionLocal)
    calls = _configure(monkeypatch, [FAIL_ENVELOPE, OK_ENVELOPE])
    monkeypatch.setattr(
        structural_loop.solver,
        "resolve_with_constraints",
        lambda cfg, ewt, approved, caps, deviation_weight=3: _adjusted_layout(),
    )

    res = await client.post(
        f"/api/projects/{pid}/structural", json={"layout_id": "A"}, headers=HDRS
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert calls["n"] == 2
    assert body["iterations_used"] == 2
    assert body["status"] == "designed"
    assert body["layout_adjusted"] is True
    joined = "\n".join(body["changelog"])
    assert "deflection" in joined
    assert "capped room spans along x" in joined
    assert "resized" in joined

    # stored layout stays the ARCHITECTURAL set; adjustment is on the design
    async with SessionLocal() as s:
        design = await s.get(StructuralDesign, body["design_id"])
        assert design.final_geometry is not None
        assert design.final_geometry["ground_floor"]["rooms"][0]["width"] == 4.0
        row = (
            await s.execute(
                StoredLayout.__table__.select().where(StoredLayout.project_id == pid)
            )
        ).first()
        assert row.geometry["ground_floor"]["rooms"][0]["width"] == 5.0


async def test_loop_caps_at_three_iterations(client_db, monkeypatch):
    client, SessionLocal = client_db
    pid = await _setup(client, SessionLocal)
    calls = _configure(monkeypatch, [FAIL_ENVELOPE])  # always failing
    monkeypatch.setattr(
        structural_loop.solver,
        "resolve_with_constraints",
        lambda cfg, ewt, approved, caps, deviation_weight=3: _adjusted_layout(),
    )

    res = await client.post(
        f"/api/projects/{pid}/structural", json={"layout_id": "A"}, headers=HDRS
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert calls["n"] == 3
    assert body["iterations_used"] == 3
    assert body["status"] == "designed_with_warnings"
    assert any("Iteration cap" in line for line in body["changelog"])


async def test_spanless_resolvable_violation_lands_in_changelog(client_db, monkeypatch):
    """Regression: a violation with a resolvable remedy_hint (reduce_span)
    but NO span_m was excluded from the re-solve list AND from the exit
    changelog (which only recorded non-resolvable hints) — the design was
    saved with warnings and an empty changelog explaining nothing."""
    client, SessionLocal = client_db
    pid = await _setup(client, SessionLocal)
    spanless = {k: v for k, v in SPAN_VIOLATION.items() if k != "span_m"}
    envelope = {
        **FAIL_ENVELOPE,
        "data": {"quantities": {}, "violations": [spanless]},
    }
    calls = _configure(monkeypatch, [envelope])

    res = await client.post(
        f"/api/projects/{pid}/structural", json={"layout_id": "A"}, headers=HDRS
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert calls["n"] == 1  # nothing actionable — no re-solve loop
    assert body["status"] == "designed_with_warnings"
    assert any(spanless["check"] in line for line in body["changelog"]), (
        f"changelog must name the unactioned violation: {body['changelog']}"
    )


async def test_loop_stops_when_resolve_infeasible(client_db, monkeypatch):
    client, SessionLocal = client_db
    pid = await _setup(client, SessionLocal)
    calls = _configure(monkeypatch, [FAIL_ENVELOPE])
    monkeypatch.setattr(
        structural_loop.solver,
        "resolve_with_constraints",
        lambda cfg, ewt, approved, caps, deviation_weight=3: None,
    )

    res = await client.post(
        f"/api/projects/{pid}/structural", json={"layout_id": "A"}, headers=HDRS
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert calls["n"] == 1
    assert body["status"] == "designed_with_warnings"
    assert body["layout_adjusted"] is False
    assert any("infeasible" in line for line in body["changelog"])


async def test_unconfident_grid_requires_confirmation(client_db, monkeypatch):
    client, SessionLocal = client_db
    geo = {
        **GEO_V1,
        "ground_floor": {**GEO_V1["ground_floor"], "columns": IRREGULAR_COLUMNS},
    }
    pid = await _setup(client, SessionLocal, geometry=geo)
    _configure(monkeypatch, [OK_ENVELOPE])

    res = await client.post(
        f"/api/projects/{pid}/structural", json={"layout_id": "A"}, headers=HDRS
    )
    assert res.status_code == 409, res.text
    assert res.json()["detail"]["code"] == "grid_needs_review"

    res = await client.post(
        f"/api/projects/{pid}/structural",
        json={"layout_id": "A", "allow_unconfident_grid": True},
        headers=HDRS,
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "designed"


# ── solver: real constrained re-solve ───────────────────────────────────────


def test_resolve_with_constraints_respects_span_cap():
    from app.engine.models import PlotConfig
    from app.engine.solver import resolve_with_constraints, solve_layouts

    cfg = PlotConfig(
        plot_length=15.0,
        plot_width=12.0,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=0.9,
        setback_right=0.9,
        num_bedrooms=2,
        toilets=2,
        parking=False,
        city="other",
        road_side="S",
        vastu_enabled=False,
    )
    layouts = solve_layouts(cfg, 0.23)
    assert layouts
    approved = layouts[0]

    cap = 3.6
    adjusted = resolve_with_constraints(cfg, 0.23, approved, {"x": cap})
    assert adjusted is not None
    for fp in (adjusted.ground_floor, adjusted.first_floor):
        for room in fp.rooms:
            assert room.width <= cap + 0.51, (
                f"{room.id} width {room.width} exceeds span cap (+snap slack)"
            )
    # identity preserved — same layout, structurally adjusted
    assert adjusted.id == approved.id


# ── concurrency guard: inflight design runs ────────────────────────────────────


def test_guard_rejects_concurrent_run_for_same_layout():
    """The guard raises DesignRunInProgress on the second call for the same layout."""
    project_id = "test-project-1"
    layout_key = "A"

    # First call: should succeed (registers the run)
    try:
        asyncio.run(
            structural_loop._check_and_register_inflight(project_id, layout_key)
        )
    except structural_loop.DesignRunInProgress:
        pytest.fail("First call should not raise DesignRunInProgress")

    # Second call for same layout: should raise
    with pytest.raises(structural_loop.DesignRunInProgress):
        asyncio.run(
            structural_loop._check_and_register_inflight(project_id, layout_key)
        )

    # Clean up
    structural_loop._unregister_inflight(project_id, layout_key)


def test_guard_allows_different_layouts():
    """The guard allows concurrent runs for different layouts of the same project."""
    project_id = "test-project-2"

    # First layout
    try:
        asyncio.run(structural_loop._check_and_register_inflight(project_id, "A"))
    except structural_loop.DesignRunInProgress:
        pytest.fail("First layout should not raise")

    # Different layout: should NOT raise (different layout_key)
    try:
        asyncio.run(structural_loop._check_and_register_inflight(project_id, "B"))
    except structural_loop.DesignRunInProgress:
        pytest.fail("Second layout should not raise (different key)")

    # Clean up
    structural_loop._unregister_inflight(project_id, "A")
    structural_loop._unregister_inflight(project_id, "B")


def test_guard_allows_rerun_after_unregister():
    """After unregistering, a new run for the same layout is allowed."""
    project_id = "test-project-3"
    layout_key = "A"

    # First run
    try:
        asyncio.run(
            structural_loop._check_and_register_inflight(project_id, layout_key)
        )
    except structural_loop.DesignRunInProgress:
        pytest.fail("First run should succeed")

    # Unregister
    structural_loop._unregister_inflight(project_id, layout_key)

    # Second run: should now be allowed
    try:
        asyncio.run(
            structural_loop._check_and_register_inflight(project_id, layout_key)
        )
    except structural_loop.DesignRunInProgress:
        pytest.fail("Second run after unregister should succeed")

    # Clean up
    structural_loop._unregister_inflight(project_id, layout_key)


async def test_design_endpoint_returns_409_on_concurrent_run(client_db, monkeypatch):
    """POST /structural returns 409 when a design is already in progress."""
    client, SessionLocal = client_db
    pid = await _setup(client, SessionLocal)

    # Configure the structural API
    monkeypatch.setattr(settings, "structural_api_url", "http://sapi.test")
    monkeypatch.setattr(settings, "structural_api_key", "k1")

    # Mock design_building to block forever (simulating a long-running call)
    wait_event = asyncio.Event()

    async def blocking_design_building(payload, *, correlation_id="", timeout=120.0):
        # Signal that we entered, then wait forever
        wait_event.set()
        await asyncio.sleep(10)  # Wait a long time
        return structagent_client.StructuralResult(
            ok=True, checks=[{"name": "all pass", "ok": True}], data={"violations": []}
        )

    monkeypatch.setattr(structagent_client, "design_building", blocking_design_building)

    # Start first request in background
    task1 = asyncio.create_task(
        client.post(
            f"/api/projects/{pid}/structural",
            json={"layout_id": "A"},
            headers=HDRS,
        )
    )

    # Wait a bit for it to get into the design_building call
    await asyncio.sleep(0.5)

    # Try second request while first is still running
    res2 = await client.post(
        f"/api/projects/{pid}/structural",
        json={"layout_id": "A"},
        headers=HDRS,
    )

    # Should get 409
    assert res2.status_code == 409, f"Expected 409, got {res2.status_code}: {res2.text}"
    body2 = res2.json()
    assert body2["detail"]["code"] == "design_in_progress"
    assert "help" in body2["detail"]

    # Cancel the first task (it was going to hang forever)
    task1.cancel()
    try:
        await task1
    except asyncio.CancelledError:
        pass
