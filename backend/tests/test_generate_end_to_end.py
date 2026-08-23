"""Task 25 — GenerateRequest → engine end to end.

Covers the wizard wire contract (Task 22) reaching the CP-SAT solver:
programme flags become rooms, the open-porch flag opens the parking room's
road-facing edge, L-plot notches are respected, and a named style preset
never forces programme on its own (spec §6).
"""

from app.engine.generator import generate_from_request
from app.schemas.project import GenerateRequest


def _req(**kw):
    base = dict(
        plot_x_extent=12.0,
        plot_y_extent=18.0,
        setback_front=3.0,
        setback_rear=1.5,
        setback_left=1.2,
        setback_right=1.2,
        num_bedrooms=3,
        toilets=2,
        parking=True,
    )
    base.update(kw)
    return GenerateRequest(**base)


def _types(layout):
    return {
        r.type for fp in (layout.ground_floor, layout.first_floor) for r in fp.rooms
    }


def test_courtyard_flag_produces_a_courtyard():
    layouts = generate_from_request(_req(programme={"courtyard"}))
    assert layouts, "no layout produced"
    assert "courtyard" in _types(layouts[0])


def test_open_car_porch_flag_sets_open_sides():
    # 12x20 rather than 12x18: at 12x18 the pre-existing navigability gate
    # rejects every solver layout for a 3BHK (unrelated to this flag), and the
    # archetype fallback cannot honour an open porch.
    layouts = generate_from_request(
        _req(plot_y_extent=20.0, programme={"car_porch_open"})
    )
    assert layouts, "no layout produced"
    porches = [
        r
        for fp in (layouts[0].ground_floor,)
        for r in fp.rooms
        if r.type in ("parking", "parking_4w", "parking_2w")
    ]
    assert porches, "no parking room generated"
    assert all(p.open_sides for p in porches), "car porch was fully walled"


def test_l_plot_request_reaches_the_solver_constraint():
    layouts = generate_from_request(
        _req(plot_template="L", notch_width=3.0, notch_depth=4.0)
    )
    assert layouts
    nx0, ny0 = 12.0 - 3.0, 18.0 - 4.0
    for r in layouts[0].ground_floor.rooms:
        for p in r.rects:
            ox = max(0.0, min(p.x + p.width, 12.0) - max(p.x, nx0))
            oy = max(0.0, min(p.y + p.depth, 18.0) - max(p.y, ny0))
            assert ox * oy < 1e-6


def test_style_preset_alone_does_not_force_programme():
    """Presets seed the FORM, not the engine — an explicit empty programme must
    be honoured even when a style is named. See spec section 6."""
    layouts = generate_from_request(_req(style_preset="Kerala", programme=set()))
    assert layouts, "no layout produced"
    assert "courtyard" not in _types(layouts[0])


async def test_generate_preview_route_validates_payload(client):
    """POST /api/generate exists and enforces the GenerateRequest contract.

    Only the 422 path is exercised here — a full solve through the route is
    already covered by the engine-level tests above and would double the
    suite's wall-clock cost.
    """
    response = await client.post("/api/generate", json={"plot_x_extent": 12.0})
    assert response.status_code == 422
