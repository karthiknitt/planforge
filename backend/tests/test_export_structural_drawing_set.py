"""Structural Drawing Set export route (GET /projects/{id}/export/structural-drawing-set).

Tests the error-path gates (approval + design requirements before export) plus
a happy-path end-to-end integration test (Task 14) that proves the full
routes -> orchestrator -> 6 sheet renderers pipeline consumes realistic
columns/beams/footings data correctly.
"""

from app.models.layout import StoredLayout
from app.models.structural import StructuralDesign
from app.services import plinth_beam_design, structagent_client

HDRS = {"X-Test-User-Id": "export-owner"}

# Realistic structapi response["data"] shape (columns/beams/footings), matching
# what Tasks 2-4's unit tests already exercise in isolation. Keyed by column
# classification ("corner"/"edge"/"interior") for columns/footings, matching
# `_FOOTING_MARK` in structural_drawing_set.py; beam key format matches
# structapi's tributary-width naming convention.
FULL_STRUCTAPI_DATA = {
    "columns": {
        "corner": {
            "b_mm": 230,
            "D_mm": 300,
            "bars": "6-16 dia",
            "n_bars": 6,
            "bar_dia": 16,
            "data": {"p_percent": 1.2, "tie_dia": 8, "tie_pitch_max": 200},
        },
        "edge": {
            "b_mm": 230,
            "D_mm": 350,
            "bars": "8-16 dia",
            "n_bars": 8,
            "bar_dia": 16,
            "data": {"p_percent": 1.5, "tie_dia": 8, "tie_pitch_max": 200},
        },
        "interior": {
            "b_mm": 300,
            "D_mm": 300,
            "bars": "8-20 dia",
            "n_bars": 8,
            "bar_dia": 20,
            "data": {"p_percent": 1.8, "tie_dia": 8, "tie_pitch_max": 175},
        },
    },
    "beams": {
        "x-span4.00-trib2.25": {
            "b_mm": 230,
            "D_mm": 450,
            "span_m": 4.0,
            "trib_width_m": 2.25,
            "n_spans": 2,
            "design": {
                "n_bars": 3,
                "bar_dia": 16,
                "doubly_reinforced": False,
                "stirrups": {"sv_provided": 150},
                "Ast_prov_mm2": 603,
            },
        },
    },
    "footings": {
        "corner": {
            "data": {
                "L_m": 1.3,
                "B_m": 1.3,
                "D_overall_mm": 400,
                "bars_x": {"dia": 12, "spacing": 150},
                "bars_y": {"dia": 12, "spacing": 150},
            }
        },
        "edge": {
            "data": {
                "L_m": 1.4,
                "B_m": 1.3,
                "D_overall_mm": 400,
                "bars_x": {"dia": 12, "spacing": 150},
                "bars_y": {"dia": 12, "spacing": 150},
            }
        },
        "interior": {
            "data": {
                "L_m": 1.6,
                "B_m": 1.6,
                "D_overall_mm": 450,
                "bars_x": {"dia": 12, "spacing": 125},
                "bars_y": {"dia": 12, "spacing": 125},
            }
        },
    },
}

# Realistic plinth-beam design keyed by the ACTUAL group keys
# `plinth_group_key(kind, round(length, 1))` produces for GEO_V1's ground-floor
# walls (verified by direct inspection of build_floor_drawing(GEO_V1) output --
# 1 internal group + 4 external groups: the kitchen's void-facing edges,
# structurally exterior since #75, no longer fall under "internal"). Using
# fabricated keys that don't match any real wall would leave every beam mark
# undrawn on the Plinth Beam Plan sheet (render_plinth_beam_plan only labels a
# wall when its recomputed group key has a matching entry -- see its docstring).
FULL_PLINTH_BEAMS_DATA = {
    "plinth-external-span1.60": {
        "b_mm": 230,
        "D_mm": 300,
        "span_m": 1.60,
        "kind": "external",
        "design": {
            "n_bars": 2,
            "bar_dia": 12,
            "doubly_reinforced": False,
            "stirrups": {"sv_provided": 150},
        },
    },
    "plinth-internal-span2.20": {
        "b_mm": 230,
        "D_mm": 300,
        "span_m": 2.20,
        "kind": "internal",
        "design": {
            "n_bars": 2,
            "bar_dia": 12,
            "doubly_reinforced": False,
            "stirrups": {"sv_provided": 150},
        },
    },
    "plinth-external-span2.60": {
        "b_mm": 230,
        "D_mm": 300,
        "span_m": 2.60,
        "kind": "external",
        "design": {
            "n_bars": 3,
            "bar_dia": 12,
            "doubly_reinforced": False,
            "stirrups": {"sv_provided": 150},
        },
    },
    "plinth-external-span3.70": {
        "b_mm": 230,
        "D_mm": 300,
        "span_m": 3.70,
        "kind": "external",
        "design": {
            "n_bars": 3,
            "bar_dia": 12,
            "doubly_reinforced": False,
            "stirrups": {"sv_provided": 150},
        },
    },
    "plinth-external-span6.70": {
        "b_mm": 230,
        "D_mm": 300,
        "span_m": 6.70,
        "kind": "external",
        "design": {
            "n_bars": 4,
            "bar_dia": 12,
            "doubly_reinforced": True,
            "stirrups": {"sv_provided": 150},
        },
    },
}

PROJECT_BODY = {
    "name": "Export Test",
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
    "ground_floor": {
        "floor": 0,
        "rooms": [
            {
                "id": "r1",
                "name": "Living",
                "type": "living",
                "x": 0.0,
                "y": 0.0,
                "width": 4.0,
                "depth": 3.5,
                "area": 14.0,
            },
            {
                "id": "r2",
                "name": "Kitchen",
                "type": "kitchen",
                "x": 4.0,
                "y": 0.0,
                "width": 2.5,
                "depth": 2.0,
                "area": 5.0,
            },
        ],
        "columns": GRID_COLUMNS,
    },
    "first_floor": {
        "floor": 1,
        "rooms": [
            {
                "id": "r3",
                "name": "Bedroom 1",
                "type": "bedroom",
                "x": 0.0,
                "y": 0.0,
                "width": 4.0,
                "depth": 3.5,
                "area": 14.0,
            }
        ],
        "columns": [],
    },
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


# ──────────────────────────────────── Error paths ────────────────────────────────────


async def test_export_structural_drawing_set_409_not_approved(client_db):
    """Layout with no approved revision -> 409 with code 'not_approved'."""
    client, SessionLocal = client_db
    project_id = await _make_project(client)
    await _seed_layout(SessionLocal, project_id, GEO_V1)

    res = await client.get(
        f"/api/projects/{project_id}/export/structural-drawing-set",
        headers=HDRS,
    )
    assert res.status_code == 409, res.text
    body = res.json()
    assert body["detail"]["code"] == "not_approved"
    assert "Approve the architectural plan first" in body["detail"]["help"]


async def test_export_structural_drawing_set_409_not_designed(client_db):
    """Layout with approval but no structural design -> 409 with code 'not_designed'."""
    client, SessionLocal = client_db
    project_id = await _make_project(client)
    await _seed_layout(SessionLocal, project_id, GEO_V1)

    # Approve the layout
    res = await client.post(
        f"/api/projects/{project_id}/structural/approve",
        json={"layout_id": "A"},
        headers=HDRS,
    )
    assert res.status_code == 200, res.text

    # Try to export without running structural design
    res = await client.get(
        f"/api/projects/{project_id}/export/structural-drawing-set",
        headers=HDRS,
    )
    assert res.status_code == 409, res.text
    body = res.json()
    assert body["detail"]["code"] == "not_designed"
    assert "Run structural design first" in body["detail"]["help"]


async def test_export_structural_drawing_set_404_missing_layout(client_db):
    """Layout ID not found -> 404."""
    client, SessionLocal = client_db
    project_id = await _make_project(client)
    await _seed_layout(SessionLocal, project_id, GEO_V1)

    res = await client.get(
        f"/api/projects/{project_id}/export/structural-drawing-set?layout_id=Z",
        headers=HDRS,
    )
    assert res.status_code == 404, res.text
    assert "Layout 'Z' not found" in res.json()["detail"]


async def test_export_structural_drawing_set_502_on_structapi_error(
    client_db, monkeypatch
):
    """Plinth beam design structapi error -> 502."""
    client, SessionLocal = client_db
    project_id = await _make_project(client)
    await _seed_layout(SessionLocal, project_id, GEO_V1)

    # Approve the layout
    res = await client.post(
        f"/api/projects/{project_id}/structural/approve",
        json={"layout_id": "A"},
        headers=HDRS,
    )
    assert res.status_code == 200, res.text
    approval_resp = res.json()
    revision_id = approval_resp["revision_id"]

    # Seed a structural design row (approved + designed)
    async with SessionLocal() as s:
        design = StructuralDesign(
            revision_id=revision_id,
            status="designed",
            structapi_response={
                "api_version": "1",
                "ok": True,
                "checks": [],
                "data": {},
            },
        )
        s.add(design)
        await s.commit()

    # Monkeypatch plinth_beam_design to raise StructuralAPIError
    async def _raise_structapi_error(walls):
        raise structagent_client.StructuralAPIError("structapi unreachable")

    monkeypatch.setattr(
        plinth_beam_design, "design_plinth_beams", _raise_structapi_error
    )

    # Try to export - should return 502
    res = await client.get(
        f"/api/projects/{project_id}/export/structural-drawing-set",
        headers=HDRS,
    )
    assert res.status_code == 502, res.text
    assert "structapi unreachable" in res.json()["detail"]


# ──────────────────────────────────── Happy path ─────────────────────────────────


async def test_export_structural_drawing_set_happy_path_all_sheets_populated(
    client_db, monkeypatch
):
    """Full happy path: approved + designed layout with realistic
    columns/beams/footings data, plus a realistic plinth-beam design (via
    monkeypatch, avoiding a real structapi HTTP call for the plinth pass) ->
    200, valid 6-page PDF, every sheet's schedule table has real content.
    """
    client, SessionLocal = client_db
    project_id = await _make_project(client)
    await _seed_layout(SessionLocal, project_id, GEO_V1)

    res = await client.post(
        f"/api/projects/{project_id}/structural/approve",
        json={"layout_id": "A"},
        headers=HDRS,
    )
    assert res.status_code == 200, res.text
    revision_id = res.json()["revision_id"]

    async with SessionLocal() as s:
        design = StructuralDesign(
            revision_id=revision_id,
            status="designed",
            structapi_response={
                "api_version": "1",
                "ok": True,
                "checks": [],
                "data": FULL_STRUCTAPI_DATA,
            },
        )
        s.add(design)
        await s.commit()

    async def _fake_design_plinth_beams(walls, **kwargs):
        return FULL_PLINTH_BEAMS_DATA

    monkeypatch.setattr(
        plinth_beam_design, "design_plinth_beams", _fake_design_plinth_beams
    )

    res = await client.get(
        f"/api/projects/{project_id}/export/structural-drawing-set",
        headers=HDRS,
    )
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/pdf"

    pdf_bytes = res.content
    assert pdf_bytes[:5] == b"%PDF-"

    from tests.helpers.pdf_png import pdf_page_text, pdf_pages

    from app.engine.structural_sheet import SHEET_REGISTER

    n_pages = pdf_pages(pdf_bytes)
    # One page per drawing at minimum; sheets whose content overflows
    # paginate onto continuation pages rather than truncating, so the count
    # is a floor, not an equality.
    assert n_pages >= len(SHEET_REGISTER), (
        f"{n_pages} pages for {len(SHEET_REGISTER)} drawings — a sheet is missing"
    )

    pages = [pdf_page_text(pdf_bytes, i).upper() for i in range(n_pages)]
    all_text = " ".join(pages)

    # Every registered drawing is present, and the sheets appear in drawing
    # order — a sheet landing out of sequence would break the set's index.
    #
    # Ordering is checked against each page's own "DRG. NO. S-xx" stamp, not
    # against a bare "S-xx" substring: a sheet legitimately cross-references
    # others ("SEE S-04 FOR COLUMN DETAILS" on the column plan), which is
    # good drafting, and matching bare numbers would read those references
    # as sheets appearing early.
    import re as _re

    stamped = [_re.findall(r"DRG\. NO\. (S-\d\d)", p) for p in pages]
    for i, marks in enumerate(stamped):
        assert len(marks) == 1, f"page {i} carries {len(marks)} drawing stamps: {marks}"
    sequence = [marks[0] for marks in stamped]

    for drg_no, title in SHEET_REGISTER:
        assert drg_no in sequence, f"drawing {drg_no} ({title}) is not in the set"
    assert sequence == sorted(sequence), f"sheets out of drawing order: {sequence}"

    # Both floors are framed. The set this replaces drew only the first
    # floor, so ground-floor framing was absent entirely.
    assert "GF ROOF" in all_text
    assert "FF ROOF" in all_text

    # Marks rendered from real data.
    assert "T1" in all_text  # corner footing mark (GEO_V1 has a corner column)
    assert "PB1" in all_text  # smallest-span plinth beam mark (1.60 m external)

    # Assertions derived from the ACTUAL reinforcement fields seeded above --
    # renderers read these via silent `.get(key, default)`, so a renamed or
    # missing key renders a placeholder rather than crashing, and mark-only
    # assertions would not catch it. These pin real values through to text.

    # FULL_STRUCTAPI_DATA["footings"]["corner"]["data"]: D_overall_mm=400,
    # bars_x={"dia": 12, "spacing": 150}.
    assert "400" in all_text
    assert "150" in all_text

    # beams["x-span4.00-trib2.25"]["design"]: n_bars=3, bar_dia=16, and
    # FULL_PLINTH_BEAMS_DATA's PB1 group: n_bars=2, bar_dia=12.
    assert "16" in all_text
    assert "12" in all_text

    # Structural sheets carry no bedroom count; the old set printed "0 BHK"
    # on every page because it reused the architectural title block.
    assert "BHK" not in all_text
