"""Canonical furniture fixtures (Phase 7 / Task 33).

Furniture used to be implemented TWICE with room-by-room drift risk — the
DXF dispatcher in cad_advanced (12 render functions, the richer of the two
and the specification) and the frontend's floor-plan-svg + furniture-overlay
— and was MISSING from the PDF outright. It now derives once, in
app/engine/furniture.py, as room-relative `Fixture` entities on
FloorDrawing; PDF, DXF and the SVG frontend all project the same shapes.

Acceptance pins:
- DXF output on layer A-FURNITURE is unchanged, entity-for-entity, against a
  golden captured from the pre-migration renderers
  (tests/fixtures/furniture_dxf_golden.json — regenerate ONLY with the
  scripted capture from a pre-migration checkout, never from the new path).
- Fixtures scale with room dimensions and never overflow their room.
- Room types with no furniture yield an empty list.
"""

import json
from pathlib import Path

import ezdxf
import pytest

from app.engine.cad_advanced import draw_furniture
from app.engine.cad_elements import FloorDrawing
from app.engine.furniture import FIXTURE_COVERED_TYPES, derive_fixtures
from app.engine.models import FloorPlan, PlotConfig, Room
from app.engine.plan_geometry import build_floor_drawing

from tests.test_plan_geometry import _room

GOLDEN = json.loads(
    (Path(__file__).parent / "fixtures" / "furniture_dxf_golden.json").read_text()
)

LAYER = "A-FURNITURE"
Z = 3.0


def _capture(msp) -> list[dict]:
    """Entity stream capture — MUST match the scripted golden capture (the
    comparison is verbatim, not semantic)."""
    stream = []
    for e in msp:
        etype = e.dxftype()
        entry = {"etype": etype, "layer": e.dxf.layer}
        try:
            entry["elevation"] = round(e.dxf.elevation, 4)
        except Exception:
            entry["elevation"] = None
        if etype == "LWPOLYLINE":
            entry["closed"] = bool(e.closed)
            entry["linetype"] = e.dxf.linetype
            entry["points"] = [
                [round(x, 4), round(y, 4)] for x, y, *_ in e.get_points()
            ]
        elif etype == "CIRCLE":
            entry["center"] = [round(e.dxf.center.x, 4), round(e.dxf.center.y, 4)]
            entry["radius"] = round(e.dxf.radius, 4)
        elif etype == "ARC":
            entry["center"] = [round(e.dxf.center.x, 4), round(e.dxf.center.y, 4)]
            entry["radius"] = round(e.dxf.radius, 4)
            entry["start_angle"] = round(e.dxf.start_angle, 4)
            entry["end_angle"] = round(e.dxf.end_angle, 4)
        elif etype == "LINE":
            st, en = e.dxf.start, e.dxf.end
            entry["start"] = [round(st.x, 4), round(st.y, 4), round(st.z, 4)]
            entry["end"] = [round(en.x, 4), round(en.y, 4), round(en.z, 4)]
        else:  # pragma: no cover - capture surface must be exhaustive
            raise AssertionError(f"unhandled etype {etype}")
        stream.append(entry)
    return stream


def _projected_stream(room: Room) -> list[dict]:
    doc = ezdxf.new()
    msp = doc.modelspace()
    draw_furniture(msp, room, derive_fixtures([room]), LAYER, Z)
    return _capture(msp)


# ── golden parity: the DXF output is unchanged, entity for entity ─────────


@pytest.mark.parametrize("case", sorted(GOLDEN))
def test_dxf_furniture_stream_matches_the_pre_migration_golden(case):
    rtype, dims = case.rsplit("@", 1)
    w, d = (float(v) for v in dims.split("x"))
    room_type = rtype if rtype != "balcony-narrow" else "balcony"
    room = Room(id="r1", name=rtype, type=room_type, x=1.25, y=2.5, width=w, depth=d)
    assert _projected_stream(room) == GOLDEN[case]


# ── coverage: which types draw, which deliberately don't ──────────────────


def test_dispatch_covers_the_twelve_dxf_room_types():
    assert FIXTURE_COVERED_TYPES == {
        "bedroom",
        "master_bedroom",
        "living",
        "dining",
        "kitchen",
        "toilet",
        "bathroom",
        "study",
        "home_office",
        "pooja",
        "balcony",
        "utility",
        "servant_quarter",
        "parking",
        "garage",
        "gym",
    }


@pytest.mark.parametrize("rtype", ["staircase", "passage", "store_room", "courtyard"])
def test_room_type_with_no_furniture_yields_an_empty_list(rtype):
    room = Room(id="r", name=rtype, type=rtype, x=0.0, y=0.0, width=3.0, depth=3.0)
    assert derive_fixtures([room]) == []


# ── scaling and overflow invariants ───────────────────────────────────────


def _shape_extents(shape) -> tuple[float, float, float, float]:
    if shape.kind == "rect":
        return shape.x, shape.y, shape.x + shape.width, shape.y + shape.depth
    if shape.kind in ("circle", "arc"):
        return (
            shape.x - shape.radius,
            shape.y - shape.radius,
            shape.x + shape.radius,
            shape.y + shape.radius,
        )
    if shape.kind == "line":
        return (
            min(shape.x, shape.x2),
            min(shape.y, shape.y2),
            max(shape.x, shape.x2),
            max(shape.y, shape.y2),
        )
    raise AssertionError(f"unknown shape kind {shape.kind!r}")


@pytest.mark.parametrize("rtype", sorted(FIXTURE_COVERED_TYPES))
@pytest.mark.parametrize("size", [(1.0, 1.0), (2.0, 3.0), (3.6, 4.4), (6.0, 8.0)])
def test_fixtures_scale_with_room_and_never_overflow(rtype, size):
    w, d = size
    room = Room(id="r", name=rtype, type=rtype, x=1.0, y=2.0, width=w, depth=d)
    for fixture in derive_fixtures([room]):
        assert fixture.room_id == "r"
        assert fixture.shapes, f"{rtype}/{fixture.kind} emitted with no shapes"
        for shape in fixture.shapes:
            x1, y1, x2, y2 = _shape_extents(shape)
            assert x1 >= -1e-6, (rtype, size, fixture.kind, shape)
            assert y1 >= -1e-6, (rtype, size, fixture.kind, shape)
            assert x2 <= w + 1e-6, (rtype, size, fixture.kind, shape)
            assert y2 <= d + 1e-6, (rtype, size, fixture.kind, shape)


def test_room_relative_placement_is_position_invariant():
    """Room-relative coordinates: the same room shape at a different plot
    position must yield byte-identical fixtures."""
    a = Room(id="r", name="Bed", type="bedroom", x=0.0, y=0.0, width=3.6, depth=4.4)
    b = Room(id="r", name="Bed", type="bedroom", x=5.0, y=7.0, width=3.6, depth=4.4)
    assert derive_fixtures([a]) == derive_fixtures([b])


# ── FloorDrawing integration and payload v2 ────────────────────────────────


def _cfg() -> PlotConfig:
    return PlotConfig(
        plot_y_extent=15.0,
        plot_x_extent=9.0,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=1.0,
        setback_right=1.0,
        num_bedrooms=2,
        toilets=1,
        parking=False,
        num_floors=1,
    )


def test_build_floor_drawing_attaches_fixtures():
    fp = FloorPlan(
        floor=0,
        floor_type="ground",
        rooms=[
            _room("bed-1", 1.23, 7.73, 3.155, 6.04),
            _room("stair-1", 4.5, 7.73, 3.27, 6.04, rtype="staircase"),
        ],
    )
    drawing = build_floor_drawing(fp, _cfg())
    kinds = {(f.room_id, f.kind) for f in drawing.fixtures}
    assert ("bed-1", "bed") in kinds
    assert all(room_id in {"bed-1", "stair-1"} for room_id, _ in kinds)
    assert not any(room_id == "stair-1" for room_id, _ in kinds)


def test_fixtures_round_trip_through_the_v2_payload():
    fp = FloorPlan(
        floor=0, floor_type="ground", rooms=[_room("bed-1", 1.23, 7.73, 3.155, 6.04)]
    )
    drawing = build_floor_drawing(fp, _cfg())
    payload = drawing.to_dict()
    assert payload["fixtures"], "v2 payload must carry fixtures"
    restored = FloorDrawing.from_dict(payload)
    # in-memory shapes hold raw floats; the payload is rounded to 4dp (as
    # with every other entity) — compare at the payload level
    assert restored.fixtures == FloorDrawing.from_dict(drawing.to_dict()).fixtures
    assert restored.to_dict() == payload


def test_v1_payload_without_fixtures_rehydrates_empty():
    """Task 28's rehydration contract: a pre-fixture payload parses with
    fixtures == [] and serialises again as current v2."""
    fp = FloorPlan(
        floor=0, floor_type="ground", rooms=[_room("bed-1", 1.23, 7.73, 3.155, 6.04)]
    )
    payload = build_floor_drawing(fp, _cfg()).to_dict()
    payload["version"] = 1
    payload.pop("fixtures", None)
    restored = FloorDrawing.from_dict(payload)
    assert restored.fixtures == []
    assert restored.to_dict()["version"] == 2


# ── PDF projection ─────────────────────────────────────────────────────────


def test_pdf_draws_fixtures_from_the_canonical_drawing():
    """Furniture shows up in the PDF: _draw_fixtures projects each shape at
    the fixture's room-translated plot coordinates."""
    from io import BytesIO

    from reportlab.pdfgen import canvas

    from app.engine.pdf import _draw_fixtures

    fp = FloorPlan(
        floor=0, floor_type="ground", rooms=[_room("bed-1", 1.23, 7.73, 3.155, 6.04)]
    )
    drawing = build_floor_drawing(fp, _cfg())
    assert drawing.fixtures

    c = canvas.Canvas(BytesIO())
    rects: list[tuple] = []
    circles: list[tuple] = []
    c.rect = lambda x, y, w, h, **kw: rects.append((x, y, w, h))  # type: ignore[method-assign]
    c.circle = lambda x, y, r, **kw: circles.append((x, y, r))  # type: ignore[method-assign]

    rooms_by_id = {r.id: r for r in fp.rooms}
    ox, oy, s = 0.0, 0.0, 2.0
    _draw_fixtures(c, drawing, rooms_by_id, s, ox, oy)

    room = fp.rooms[0]
    assert rects, "PDF must stroke the furniture rects"
    # every projected rect plot-coordinate equals room + room-relative shape
    for x, y, w, h in rects:
        assert room.x <= x / s <= room.x + room.width
        assert room.y <= y / s <= room.y + room.depth
    assert circles, "PDF must stroke the pillow/side-table circles"
