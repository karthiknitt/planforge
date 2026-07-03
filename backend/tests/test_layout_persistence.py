"""Regression tests for the A1 keystone: layouts are persisted once and every
consumer (viewer, share view, exports, revisions, edits) reads the SAME
stored geometry.

Previously every endpoint re-ran the CP-SAT solver independently: the share
view could show a different plan than the engineer saw, exports ignored
edits, and edits lived in process memory that Cloud Run wiped on cold start.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.layout import StoredLayout
from app.models.user import User

HDRS = {"X-Test-User-Id": "layout-owner"}

PROJECT_BODY = {
    "name": "Persistence Test",
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


def _pdf_contains(pdf: bytes, needle: str) -> bool:
    """ReportLab embeds subset fonts (glyph-index hex strings), so extract
    text properly with pymupdf instead of grepping the byte stream."""
    import fitz

    doc = fitz.open(stream=pdf, filetype="pdf")
    text = "".join(page.get_text() for page in doc)
    doc.close()
    return needle in text


async def _make_project(client) -> str:
    res = await client.post("/api/projects", json=PROJECT_BODY, headers=HDRS)
    assert res.status_code == 201, res.text
    return res.json()["id"]


async def _tamper_first_layout(sf, project_id: str, new_room_name: str) -> str:
    """Rename the first room of the first stored layout directly in the DB.
    Returns the layout_key. Consumers that truly read the store will see it."""
    async with sf() as session:
        result = await session.execute(
            select(StoredLayout).where(StoredLayout.project_id == project_id)
        )
        stored = result.scalars().first()
        geometry = dict(stored.geometry)
        gf = dict(geometry["ground_floor"])
        rooms = [dict(r) for r in gf["rooms"]]
        # Rename the living room — staircases are drawn as symbols in the
        # PDF, not name labels, so rooms[0] would be invisible there
        target = next((i for i, r in enumerate(rooms) if r["type"] == "living"), 0)
        rooms[target]["name"] = new_room_name
        gf["rooms"] = rooms
        geometry["ground_floor"] = gf
        stored.geometry = geometry
        await session.commit()
        return stored.layout_key


async def test_generate_persists_layouts(client_db):
    client, sf = client_db
    pid = await _make_project(client)
    res = await client.get(f"/api/projects/{pid}/generate", headers=HDRS)
    assert res.status_code == 200, res.text
    async with sf() as session:
        rows = (
            (
                await session.execute(
                    select(StoredLayout).where(StoredLayout.project_id == pid)
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == len(res.json()["layouts"]) > 0
    assert all(r.source == "solver" for r in rows)


async def test_second_generate_returns_stored_not_resolved(client_db):
    client, _ = client_db
    pid = await _make_project(client)
    first = (await client.get(f"/api/projects/{pid}/generate", headers=HDRS)).json()
    second = (await client.get(f"/api/projects/{pid}/generate", headers=HDRS)).json()
    # Identical geometry proves the second call read the store — a fresh
    # CP-SAT run has no such guarantee.
    assert first == second


async def test_refresh_replaces_stored_layouts(client_db):
    client, sf = client_db
    pid = await _make_project(client)
    await client.get(f"/api/projects/{pid}/generate", headers=HDRS)
    key = await _tamper_first_layout(sf, pid, "TAMPERED-ROOM")

    res = await client.get(
        f"/api/projects/{pid}/generate", params={"refresh": "true"}, headers=HDRS
    )
    assert res.status_code == 200
    body = res.json()
    # Regeneration discards the tampered edit
    assert "TAMPERED-ROOM" not in str(body)
    assert key  # sanity


async def test_share_view_reads_stored_geometry(client_db):
    client, sf = client_db
    pid = await _make_project(client)
    await client.get(f"/api/projects/{pid}/generate", headers=HDRS)
    await _tamper_first_layout(sf, pid, "SHARED-TAMPER")

    token = (await client.post(f"/api/projects/{pid}/share", headers=HDRS)).json()[
        "token"
    ]
    res = await client.get(f"/api/share/{token}")
    assert res.status_code == 200
    assert "SHARED-TAMPER" in str(res.json())


async def test_export_pdf_reads_stored_geometry(client_db):
    client, sf = client_db
    pid = await _make_project(client)
    await client.get(f"/api/projects/{pid}/generate", headers=HDRS)
    key = await _tamper_first_layout(sf, pid, "EXPORT-TAMPER")

    res = await client.get(
        f"/api/projects/{pid}/export/pdf", params={"layout_id": key}, headers=HDRS
    )
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    # The tampered room label must appear in the PDF text — content streams
    # are Flate-compressed, so decompress before searching
    assert _pdf_contains(res.content, "EXPORT-TAMPER")


async def test_revision_snapshot_reads_stored_geometry(client_db):
    client, sf = client_db
    pid = await _make_project(client)
    await client.get(f"/api/projects/{pid}/generate", headers=HDRS)
    await _tamper_first_layout(sf, pid, "REVISION-TAMPER")

    res = await client.post(
        f"/api/projects/{pid}/revisions", json={"label": "test"}, headers=HDRS
    )
    assert res.status_code == 201, res.text
    version = res.json()["version"]
    detail = await client.get(f"/api/projects/{pid}/revisions/{version}", headers=HDRS)
    assert "REVISION-TAMPER" in str(detail.json())


class TestLayoutPatch:
    async def _pro_user(self, sf, user_id="layout-owner"):
        async with sf() as session:
            session.add(
                User(
                    id=user_id,
                    plan_tier="pro",
                    plan_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                )
            )
            await session.commit()

    async def _setup(self, client, sf):
        await self._pro_user(sf)
        pid = await _make_project(client)
        gen = (await client.get(f"/api/projects/{pid}/generate", headers=HDRS)).json()
        layout = gen["layouts"][0]
        return pid, layout

    @staticmethod
    def _rooms_payload(layout: dict) -> list[dict]:
        return [
            {
                "id": r["id"],
                "type": r["type"],
                "name": r["name"],
                "x": r["x"],
                "y": r["y"],
                "width": r["width"],
                "height": r["depth"],
                "floor": "gf",
            }
            for r in layout["ground_floor"]["rooms"]
        ] + [
            {
                "id": r["id"],
                "type": r["type"],
                "name": r["name"],
                "x": r["x"],
                "y": r["y"],
                "width": r["width"],
                "height": r["depth"],
                "floor": "ff",
            }
            for r in layout["first_floor"]["rooms"]
        ]

    async def test_patch_persists_moved_room(self, client_db):
        client, sf = client_db
        pid, layout = await self._setup(client, sf)
        rooms = self._rooms_payload(layout)
        # Nudge the first GF room by 10 cm — position (x/y), not just size
        rooms[0]["x"] = round(rooms[0]["x"] + 0.1, 3)
        res = await client.patch(
            f"/api/projects/{pid}/layouts/{layout['id']}",
            json={"rooms": rooms},
            headers=HDRS,
        )
        assert res.status_code == 200, res.text

        # The stored layout now carries the new position and is marked edited
        gen = (await client.get(f"/api/projects/{pid}/generate", headers=HDRS)).json()
        stored_layout = next(lay for lay in gen["layouts"] if lay["id"] == layout["id"])
        assert stored_layout["ground_floor"]["rooms"][0]["x"] == rooms[0]["x"]
        async with sf() as session:
            row = (
                await session.execute(
                    select(StoredLayout).where(
                        StoredLayout.project_id == pid,
                        StoredLayout.layout_key == layout["id"],
                    )
                )
            ).scalar_one()
            assert row.source == "edited"

    async def test_patch_requires_pro(self, client_db):
        client, sf = client_db
        pid = await _make_project(client)  # no pro user row
        gen = (await client.get(f"/api/projects/{pid}/generate", headers=HDRS)).json()
        layout = gen["layouts"][0]
        res = await client.patch(
            f"/api/projects/{pid}/layouts/{layout['id']}",
            json={"rooms": self._rooms_payload(layout)},
            headers=HDRS,
        )
        assert res.status_code == 403

    async def test_patch_unknown_layout_404(self, client_db):
        client, sf = client_db
        pid, layout = await self._setup(client, sf)
        res = await client.patch(
            f"/api/projects/{pid}/layouts/no-such-layout",
            json={"rooms": self._rooms_payload(layout)},
            headers=HDRS,
        )
        assert res.status_code == 404
