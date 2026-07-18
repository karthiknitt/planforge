"""Stage 2 revision lifecycle: Draft -> Approved -> Designed (+ stale).

Architectural revisions are immutable snapshots created at approval time;
structural designs hang off a revision; any geometry edit that no longer
matches the approved snapshot's hash drops the layout back to Draft and
marks dependent designs stale.
"""

import httpx

from app.config.settings import settings
from app.models.layout import StoredLayout
from app.models.structural import ArchitecturalRevision, StructuralDesign
from app.services import layout_store, structagent_client, structural_store

HDRS = {"X-Test-User-Id": "revision-owner"}

PROJECT_BODY = {
    "name": "Revision Test",
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

GEO_V1 = {
    "id": "A",
    "name": "Layout A",
    "ground_floor": {"floor": 0, "rooms": [], "columns": GRID_COLUMNS},
    "first_floor": {"floor": 1, "rooms": [], "columns": []},
}

# Geometry edit that actually moves a room — the geometry_hash is scoped to
# room fields only, so an edit that just touches metadata (e.g. `name`) is
# no longer expected to invalidate a design; it must change a room.
EDITED_GEO_V1 = {
    **GEO_V1,
    "ground_floor": {
        "floor": 0,
        "rooms": [
            {
                "id": "r1",
                "name": "Living",
                "type": "living",
                "x": 1.0,
                "y": 0.0,
                "width": 4.0,
                "depth": 3.5,
                "area": 14.0,
            }
        ],
        "columns": GRID_COLUMNS,
    },
}

# A third, distinct geometry (different room width) — used to prove that an
# edit that never returns to the approved hash keeps the design stale.
EDITED_GEO_V2 = {
    **GEO_V1,
    "ground_floor": {
        "floor": 0,
        "rooms": [
            {
                "id": "r1",
                "name": "Living",
                "type": "living",
                "x": 1.0,
                "y": 0.0,
                "width": 5.0,
                "depth": 3.5,
                "area": 17.5,
            }
        ],
        "columns": GRID_COLUMNS,
    },
}

ENVELOPE = {
    "api_version": "1",
    "ok": True,
    "checks": [{"name": "columns/interior: biaxial interaction <= 1.0", "ok": True}],
    "data": {
        "quantities": {"steel_kg": {"total": 1234.5}, "concrete_m3": {"total": 21.0}},
        "violations": [],
    },
    "artifacts": [],
    "disclaimer": "verify against official BIS copies",
}


async def _make_project(client) -> str:
    res = await client.post("/api/projects", json=PROJECT_BODY, headers=HDRS)
    assert res.status_code == 201, res.text
    return res.json()["id"]


async def _seed_layout(SessionLocal, project_id: str, geometry: dict) -> str:
    async with SessionLocal() as s:
        row = StoredLayout(
            project_id=project_id,
            layout_key="A",
            source="solver",
            geometry=geometry,
        )
        s.add(row)
        await s.commit()
        return row.id


def test_geometry_hash_deterministic_and_key_order_insensitive():
    h1 = structural_store.geometry_hash(GEO_V1)
    h2 = structural_store.geometry_hash(
        {"b": {"nested": True}, **GEO_V1}
    )  # extra unrelated top-level key
    assert h1 == h2
    moved = {
        **GEO_V1,
        "ground_floor": {
            **GEO_V1["ground_floor"],
            "rooms": [
                {
                    "id": "r1",
                    "name": "Living",
                    "type": "living",
                    "x": 1.0,
                    "y": 0.0,
                    "width": 4.0,
                    "depth": 3.5,
                    "area": 14.0,
                }
            ],
        },
    }
    assert h1 != structural_store.geometry_hash(moved)


async def test_approve_creates_revision(client_db):
    client, SessionLocal = client_db
    pid = await _make_project(client)
    await _seed_layout(SessionLocal, pid, GEO_V1)

    res = await client.post(
        f"/api/projects/{pid}/structural/approve",
        json={"layout_id": "A"},
        headers=HDRS,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["created"] is True
    assert body["status"] == "approved"
    assert body["geometry_hash"] == structural_store.geometry_hash(GEO_V1)

    async with SessionLocal() as s:
        rev = await s.get(ArchitecturalRevision, body["revision_id"])
        assert rev is not None
        assert rev.project_id == pid
        assert rev.layout_key == "A"
        assert rev.geometry == GEO_V1
        assert rev.approved_by == "revision-owner"


async def test_approve_is_idempotent(client_db):
    client, SessionLocal = client_db
    pid = await _make_project(client)
    await _seed_layout(SessionLocal, pid, GEO_V1)

    first = (
        await client.post(
            f"/api/projects/{pid}/structural/approve",
            json={"layout_id": "A"},
            headers=HDRS,
        )
    ).json()
    second = (
        await client.post(
            f"/api/projects/{pid}/structural/approve",
            json={"layout_id": "A"},
            headers=HDRS,
        )
    ).json()
    assert second["revision_id"] == first["revision_id"]
    assert second["created"] is False


async def test_status_draft_then_approved(client_db):
    client, SessionLocal = client_db
    pid = await _make_project(client)
    await _seed_layout(SessionLocal, pid, GEO_V1)

    res = await client.get(
        f"/api/projects/{pid}/structural/status",
        params={"layout_id": "A"},
        headers=HDRS,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "draft"

    await client.post(
        f"/api/projects/{pid}/structural/approve",
        json={"layout_id": "A"},
        headers=HDRS,
    )
    res = await client.get(
        f"/api/projects/{pid}/structural/status",
        params={"layout_id": "A"},
        headers=HDRS,
    )
    body = res.json()
    assert body["status"] == "approved"
    assert body["revision_id"] is not None
    assert body["design"] is None


async def test_design_endpoint_409_without_approval(client_db, monkeypatch):
    client, SessionLocal = client_db
    pid = await _make_project(client)
    await _seed_layout(SessionLocal, pid, GEO_V1)
    monkeypatch.setattr(settings, "structural_api_url", "http://sapi.test")

    res = await client.post(
        f"/api/projects/{pid}/structural", json={"layout_id": "A"}, headers=HDRS
    )
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert detail["code"] == "not_approved"
    assert "approve" in detail["help"].lower()


async def test_design_persists_after_approval(client_db, monkeypatch):
    client, SessionLocal = client_db
    pid = await _make_project(client)
    await _seed_layout(SessionLocal, pid, GEO_V1)
    monkeypatch.setattr(settings, "structural_api_url", "http://sapi.test")
    monkeypatch.setattr(settings, "structural_api_key", "k1")
    monkeypatch.setattr(
        structagent_client,
        "_transport_for_tests",
        httpx.MockTransport(lambda request: httpx.Response(200, json=ENVELOPE)),
    )

    await client.post(
        f"/api/projects/{pid}/structural/approve",
        json={"layout_id": "A"},
        headers=HDRS,
    )
    res = await client.post(
        f"/api/projects/{pid}/structural", json={"layout_id": "A"}, headers=HDRS
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["revision_id"]
    assert body["design_id"]
    assert body["status"] == "designed"

    async with SessionLocal() as s:
        design = await s.get(StructuralDesign, body["design_id"])
        assert design is not None
        assert design.revision_id == body["revision_id"]
        assert design.status == "designed"
        assert design.structapi_response["data"]["quantities"]["steel_kg"]["total"] == (
            1234.5
        )

    # status endpoint now reports the designed state
    res = await client.get(
        f"/api/projects/{pid}/structural/status",
        params={"layout_id": "A"},
        headers=HDRS,
    )
    body = res.json()
    assert body["status"] == "designed"
    assert body["design"]["id"]


async def test_geometry_edit_invalidates_design(client_db, monkeypatch):
    client, SessionLocal = client_db
    pid = await _make_project(client)
    await _seed_layout(SessionLocal, pid, GEO_V1)
    monkeypatch.setattr(settings, "structural_api_url", "http://sapi.test")
    monkeypatch.setattr(settings, "structural_api_key", "k1")
    monkeypatch.setattr(
        structagent_client,
        "_transport_for_tests",
        httpx.MockTransport(lambda request: httpx.Response(200, json=ENVELOPE)),
    )
    await client.post(
        f"/api/projects/{pid}/structural/approve",
        json={"layout_id": "A"},
        headers=HDRS,
    )
    res = await client.post(
        f"/api/projects/{pid}/structural", json={"layout_id": "A"}, headers=HDRS
    )
    design_id = res.json()["design_id"]

    # edit the geometry through the canonical edit path
    edited = EDITED_GEO_V1
    async with SessionLocal() as s:
        row = await layout_store.get_stored_layout(pid, "A", s)
        await layout_store.save_edited_geometry(row, edited, s)

    async with SessionLocal() as s:
        design = await s.get(StructuralDesign, design_id)
        assert design.status == "stale"

    res = await client.get(
        f"/api/projects/{pid}/structural/status",
        params={"layout_id": "A"},
        headers=HDRS,
    )
    assert res.json()["status"] == "draft"


async def test_design_with_warnings_status(client_db, monkeypatch):
    client, SessionLocal = client_db
    pid = await _make_project(client)
    await _seed_layout(SessionLocal, pid, GEO_V1)
    failing = {
        **ENVELOPE,
        "ok": False,
        "data": {
            **ENVELOPE["data"],
            "violations": [
                {
                    "member_type": "beam",
                    "axis": "x",
                    "grid_ref": "beam line y=0, span 0",
                    "span_m": 8.0,
                    "check": "deflection L/d (cl 23.2.1)",
                    "actual": 32.0,
                    "limit": 26.0,
                    "unit": "ratio",
                    "remedy_hint": "reduce_span",
                }
            ],
        },
    }
    monkeypatch.setattr(settings, "structural_api_url", "http://sapi.test")
    monkeypatch.setattr(settings, "structural_api_key", "k1")
    monkeypatch.setattr(
        structagent_client,
        "_transport_for_tests",
        httpx.MockTransport(lambda request: httpx.Response(200, json=failing)),
    )
    await client.post(
        f"/api/projects/{pid}/structural/approve",
        json={"layout_id": "A"},
        headers=HDRS,
    )
    res = await client.post(
        f"/api/projects/{pid}/structural", json={"layout_id": "A"}, headers=HDRS
    )
    assert res.status_code == 200
    assert res.json()["status"] == "designed_with_warnings"


async def test_mark_designs_stale_scoped_to_project(client_db):
    _, SessionLocal = client_db
    async with SessionLocal() as s:
        rev = ArchitecturalRevision(
            project_id="p1",
            layout_key="A",
            geometry=GEO_V1,
            geometry_hash=structural_store.geometry_hash(GEO_V1),
            approved_by="u1",
        )
        s.add(rev)
        await s.flush()
        s.add(StructuralDesign(revision_id=rev.id, status="designed"))
        await s.commit()

    async with SessionLocal() as s:
        n = await structural_store.mark_designs_stale("p1", s)
        await s.commit()
        assert n == 1
        n2 = await structural_store.mark_designs_stale("p1", s)
        assert n2 == 0  # idempotent: already stale


async def test_get_design_409_when_not_approved(client_db):
    client, SessionLocal = client_db
    pid = await _make_project(client)
    await _seed_layout(SessionLocal, pid, GEO_V1)

    res = await client.get(
        f"/api/projects/{pid}/structural/design",
        params={"layout_id": "A"},
        headers=HDRS,
    )
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "not_approved"


async def test_get_design_404_when_approved_but_not_designed(client_db):
    client, SessionLocal = client_db
    pid = await _make_project(client)
    await _seed_layout(SessionLocal, pid, GEO_V1)
    await client.post(
        f"/api/projects/{pid}/structural/approve",
        json={"layout_id": "A"},
        headers=HDRS,
    )

    res = await client.get(
        f"/api/projects/{pid}/structural/design",
        params={"layout_id": "A"},
        headers=HDRS,
    )
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "not_designed"


async def test_get_design_returns_persisted_design(client_db, monkeypatch):
    client, SessionLocal = client_db
    pid = await _make_project(client)
    await _seed_layout(SessionLocal, pid, GEO_V1)
    monkeypatch.setattr(settings, "structural_api_url", "http://sapi.test")
    monkeypatch.setattr(settings, "structural_api_key", "k1")
    monkeypatch.setattr(
        structagent_client,
        "_transport_for_tests",
        httpx.MockTransport(lambda request: httpx.Response(200, json=ENVELOPE)),
    )
    await client.post(
        f"/api/projects/{pid}/structural/approve",
        json={"layout_id": "A"},
        headers=HDRS,
    )
    design_res = await client.post(
        f"/api/projects/{pid}/structural", json={"layout_id": "A"}, headers=HDRS
    )
    design_id = design_res.json()["design_id"]

    res = await client.get(
        f"/api/projects/{pid}/structural/design",
        params={"layout_id": "A"},
        headers=HDRS,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["design_id"] == design_id
    assert body["status"] == "designed"
    assert body["structapi"]["data"]["quantities"]["steel_kg"]["total"] == 1234.5
    assert body["structapi"]["disclaimer"] == ENVELOPE["disclaimer"]
    assert body["changelog"] == []
    assert body["final_geometry"] is None


async def test_get_design_409_after_geometry_edit_invalidates(client_db, monkeypatch):
    client, SessionLocal = client_db
    pid = await _make_project(client)
    await _seed_layout(SessionLocal, pid, GEO_V1)
    monkeypatch.setattr(settings, "structural_api_url", "http://sapi.test")
    monkeypatch.setattr(settings, "structural_api_key", "k1")
    monkeypatch.setattr(
        structagent_client,
        "_transport_for_tests",
        httpx.MockTransport(lambda request: httpx.Response(200, json=ENVELOPE)),
    )
    await client.post(
        f"/api/projects/{pid}/structural/approve",
        json={"layout_id": "A"},
        headers=HDRS,
    )
    await client.post(
        f"/api/projects/{pid}/structural", json={"layout_id": "A"}, headers=HDRS
    )

    edited = EDITED_GEO_V1
    async with SessionLocal() as s:
        row = await layout_store.get_stored_layout(pid, "A", s)
        await layout_store.save_edited_geometry(row, edited, s)

    res = await client.get(
        f"/api/projects/{pid}/structural/design",
        params={"layout_id": "A"},
        headers=HDRS,
    )
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "not_approved"


def _mock_structapi(monkeypatch, envelope=ENVELOPE):
    monkeypatch.setattr(settings, "structural_api_url", "http://sapi.test")
    monkeypatch.setattr(settings, "structural_api_key", "k1")
    monkeypatch.setattr(
        structagent_client,
        "_transport_for_tests",
        httpx.MockTransport(lambda request: httpx.Response(200, json=envelope)),
    )


async def test_revert_to_approved_hash_resurrects_design(client_db, monkeypatch):
    """approve G1 -> design D1 -> edit to G2 (D1 stale) -> edit back to G1:
    the reverted geometry matches R1 again, so D1 must be resurrected — status
    reports designed and GET .../design returns the design (not 404)."""
    client, SessionLocal = client_db
    pid = await _make_project(client)
    await _seed_layout(SessionLocal, pid, GEO_V1)
    _mock_structapi(monkeypatch)
    await client.post(
        f"/api/projects/{pid}/structural/approve",
        json={"layout_id": "A"},
        headers=HDRS,
    )
    design_id = (
        await client.post(
            f"/api/projects/{pid}/structural", json={"layout_id": "A"}, headers=HDRS
        )
    ).json()["design_id"]

    # edit away — design goes stale (existing behaviour)
    async with SessionLocal() as s:
        row = await layout_store.get_stored_layout(pid, "A", s)
        await layout_store.save_edited_geometry(row, EDITED_GEO_V1, s)
    async with SessionLocal() as s:
        assert (await s.get(StructuralDesign, design_id)).status == "stale"
    res = await client.get(
        f"/api/projects/{pid}/structural/status",
        params={"layout_id": "A"},
        headers=HDRS,
    )
    assert res.json()["status"] == "draft"

    # edit back to the approved geometry — resurrect
    async with SessionLocal() as s:
        row = await layout_store.get_stored_layout(pid, "A", s)
        await layout_store.save_edited_geometry(row, GEO_V1, s)

    async with SessionLocal() as s:
        design = await s.get(StructuralDesign, design_id)
        assert design.status == "designed"
        assert design.pre_stale_status is None

    res = await client.get(
        f"/api/projects/{pid}/structural/status",
        params={"layout_id": "A"},
        headers=HDRS,
    )
    assert res.json()["status"] == "designed"

    res = await client.get(
        f"/api/projects/{pid}/structural/design",
        params={"layout_id": "A"},
        headers=HDRS,
    )
    assert res.status_code == 200, res.text
    assert res.json()["design_id"] == design_id


async def test_edit_never_returning_keeps_design_stale(client_db, monkeypatch):
    """Edit to G2 then G3 (never back to G1): the design stays stale."""
    client, SessionLocal = client_db
    pid = await _make_project(client)
    await _seed_layout(SessionLocal, pid, GEO_V1)
    _mock_structapi(monkeypatch)
    await client.post(
        f"/api/projects/{pid}/structural/approve",
        json={"layout_id": "A"},
        headers=HDRS,
    )
    design_id = (
        await client.post(
            f"/api/projects/{pid}/structural", json={"layout_id": "A"}, headers=HDRS
        )
    ).json()["design_id"]

    for geo in (EDITED_GEO_V1, EDITED_GEO_V2):
        async with SessionLocal() as s:
            row = await layout_store.get_stored_layout(pid, "A", s)
            await layout_store.save_edited_geometry(row, geo, s)

    async with SessionLocal() as s:
        design = await s.get(StructuralDesign, design_id)
        assert design.status == "stale"
        # first edit recorded the pre-stale status; the second edit is a no-op
        # for staling (already stale) and must not clobber it.
        assert design.pre_stale_status == "designed"

    res = await client.get(
        f"/api/projects/{pid}/structural/status",
        params={"layout_id": "A"},
        headers=HDRS,
    )
    assert res.json()["status"] == "draft"


async def test_superseded_design_not_resurrected(client_db, monkeypatch):
    """A superseded design is never staled nor resurrected by the edit path."""
    client, SessionLocal = client_db
    pid = await _make_project(client)
    await _seed_layout(SessionLocal, pid, GEO_V1)
    _mock_structapi(monkeypatch)
    approve = (
        await client.post(
            f"/api/projects/{pid}/structural/approve",
            json={"layout_id": "A"},
            headers=HDRS,
        )
    ).json()
    revision_id = approve["revision_id"]

    async with SessionLocal() as s:
        s.add(StructuralDesign(revision_id=revision_id, status="superseded"))
        await s.commit()

    # edit away and back
    async with SessionLocal() as s:
        row = await layout_store.get_stored_layout(pid, "A", s)
        await layout_store.save_edited_geometry(row, EDITED_GEO_V1, s)
    async with SessionLocal() as s:
        row = await layout_store.get_stored_layout(pid, "A", s)
        await layout_store.save_edited_geometry(row, GEO_V1, s)

    async with SessionLocal() as s:
        result = await s.execute(
            StructuralDesign.__table__.select().where(
                StructuralDesign.revision_id == revision_id
            )
        )
        rows = result.fetchall()
        assert len(rows) == 1
        assert rows[0].status == "superseded"
        assert rows[0].pre_stale_status is None


async def test_pre_stale_status_round_trip(client_db, monkeypatch):
    """pre_stale_status captures the prior status on staling and clears on
    resurrection (round-trip for the approach-(a) column)."""
    client, SessionLocal = client_db
    pid = await _make_project(client)
    await _seed_layout(SessionLocal, pid, GEO_V1)
    _mock_structapi(monkeypatch)
    await client.post(
        f"/api/projects/{pid}/structural/approve",
        json={"layout_id": "A"},
        headers=HDRS,
    )
    design_id = (
        await client.post(
            f"/api/projects/{pid}/structural", json={"layout_id": "A"}, headers=HDRS
        )
    ).json()["design_id"]

    async with SessionLocal() as s:
        design = await s.get(StructuralDesign, design_id)
        assert design.status == "designed"
        assert design.pre_stale_status is None

    async with SessionLocal() as s:
        row = await layout_store.get_stored_layout(pid, "A", s)
        await layout_store.save_edited_geometry(row, EDITED_GEO_V1, s)
    async with SessionLocal() as s:
        design = await s.get(StructuralDesign, design_id)
        assert design.status == "stale"
        assert design.pre_stale_status == "designed"

    async with SessionLocal() as s:
        row = await layout_store.get_stored_layout(pid, "A", s)
        await layout_store.save_edited_geometry(row, GEO_V1, s)
    async with SessionLocal() as s:
        design = await s.get(StructuralDesign, design_id)
        assert design.status == "designed"
        assert design.pre_stale_status is None
