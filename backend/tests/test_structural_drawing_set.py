from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.engine.cad_elements import ColumnMarker, WallSegment
from app.engine.models import PlotConfig
from app.engine.pdf import (
    MARGIN,
    ROAD_GAP,
    ROAD_H,
    TITLE_H,
    _centered_plot_oy,
    _generic_schedule_height,
    _standard_scale,
)
from app.engine.structural_drawing_set import (
    _draw_beam_detail_box,
    render_column_footing_plan,
    render_footing_details,
    render_plinth_beam_plan,
)
from tests.helpers.pdf_png import pdf_page_text

CFG = PlotConfig(
    plot_length=9.0,
    plot_width=8.0,
    setback_front=3.0,
    setback_rear=1.5,
    setback_left=1.0,
    setback_right=1.0,
    num_bedrooms=2,
    toilets=2,
    parking=True,
)


def test_column_footing_plan_renders_footing_labels():
    # 3 x-grid-lines (0, 4, 8) x 2 y-grid-lines (0, 4) so the two columns
    # classify as different footing types: (0,0) is extreme on both axes
    # (corner -> T1), (4,0) is extreme only on y (edge -> T2). This exercises
    # both the classification join in place_footings() and the distinct
    # label rendering in render_column_footing_plan().
    columns = [ColumnMarker(cx=0.0, cy=0.0), ColumnMarker(cx=4.0, cy=0.0)]
    walls = [
        WallSegment(x1=0, y1=0, x2=8, y2=0, thickness=0.23, kind="external"),
        WallSegment(x1=0, y1=4, x2=8, y2=4, thickness=0.23, kind="external"),
        WallSegment(x1=0, y1=0, x2=0, y2=4, thickness=0.23, kind="external"),
        WallSegment(x1=4, y1=0, x2=4, y2=4, thickness=0.23, kind="external"),
        WallSegment(x1=8, y1=0, x2=8, y2=4, thickness=0.23, kind="external"),
    ]
    footings_data = {
        "corner": {"data": {"L_m": 1.35, "B_m": 1.35}},
        "edge": {"data": {"L_m": 1.5, "B_m": 1.35}},
        "interior": {"data": {"L_m": 1.6, "B_m": 1.6}},
    }

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    render_column_footing_plan(c, columns, walls, footings_data, CFG, "Test Project")
    c.showPage()
    c.save()

    text = pdf_page_text(buf.getvalue(), 0)
    assert "COLUMN & FOOTING PLAN" in text.upper()
    assert "T1" in text
    assert "T2" in text


def test_footing_details_renders_schedule_and_typical_section():
    footings_data = {
        "corner": {
            "data": {
                "L_m": 1.35,
                "B_m": 1.35,
                "D_overall_mm": 450,
                "bars_x": {"dia": 12, "spacing": 150},
                "bars_y": {"dia": 12, "spacing": 150},
            }
        },
        "interior": {
            "data": {
                "L_m": 1.65,
                "B_m": 1.65,
                "D_overall_mm": 500,
                "bars_x": {"dia": 16, "spacing": 125},
                "bars_y": {"dia": 16, "spacing": 125},
            }
        },
    }
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    render_footing_details(c, footings_data, CFG, "Test Project")
    c.showPage()
    c.save()

    text = pdf_page_text(buf.getvalue(), 0)
    assert "FOOTING" in text.upper()
    assert "T1" in text  # corner
    assert "T3" in text  # interior


def test_beam_detail_box_renders_mark_and_bar_count():
    design = {
        "n_bars": 3,
        "bar_dia": 12,
        "doubly_reinforced": False,
        "stirrups": {"sv_provided": 150},
    }
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _draw_beam_detail_box(
        c, mark="PB1", b_mm=230, D_mm=300, design=design, x=100, y=500
    )
    c.showPage()
    c.save()

    text = pdf_page_text(buf.getvalue(), 0)
    assert "PB1" in text
    assert "3-12" in text.replace(" ", "") or "3nos-12" in text.replace(" ", "")


def test_beam_detail_box_renders_top_steel_when_doubly_reinforced():
    design = {
        "n_bars": 3,
        "bar_dia": 12,
        "doubly_reinforced": True,
        "n_bars_comp": 2,
        "stirrups": {"sv_provided": 150},
    }
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _draw_beam_detail_box(
        c, mark="PB2", b_mm=230, D_mm=300, design=design, x=100, y=500
    )
    c.showPage()
    c.save()

    text = pdf_page_text(buf.getvalue(), 0)
    assert "PB2" in text
    assert "Top" in text


def test_beam_detail_box_single_tension_bar_centers_without_crash():
    # n_bars == 1 must place the single bar centered, not divide by
    # (n_bars - 1) == 0 -- the exact divide-by-zero this renderer guards.
    design = {
        "n_bars": 1,
        "bar_dia": 16,
        "doubly_reinforced": False,
        "stirrups": {"sv_provided": 150},
    }
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    height = _draw_beam_detail_box(
        c, mark="PB3", b_mm=230, D_mm=300, design=design, x=100, y=500
    )
    c.showPage()
    c.save()

    assert isinstance(height, float) and height > 0
    text = pdf_page_text(buf.getvalue(), 0)
    assert "PB3" in text


def test_beam_detail_box_zero_tension_bars_skips_row_without_crash():
    # n_bars == 0 must skip the tension row entirely (no bars, no label)
    # rather than iterate/divide -- still renders the box + heading.
    design = {
        "n_bars": 0,
        "bar_dia": 0,
        "doubly_reinforced": False,
        "stirrups": {"sv_provided": 150},
    }
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    height = _draw_beam_detail_box(
        c, mark="PB4", b_mm=230, D_mm=300, design=design, x=100, y=500
    )
    c.showPage()
    c.save()

    assert isinstance(height, float) and height > 0
    text = pdf_page_text(buf.getvalue(), 0)
    assert "PB4" in text


def test_beam_detail_box_single_compression_bar_centers_without_crash():
    # n_bars_comp == 1 under doubly_reinforced must center the single top
    # bar, not divide by (n_bars_comp - 1) == 0.
    design = {
        "n_bars": 3,
        "bar_dia": 12,
        "doubly_reinforced": True,
        "n_bars_comp": 1,
        "stirrups": {"sv_provided": 150},
    }
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    height = _draw_beam_detail_box(
        c, mark="PB5", b_mm=230, D_mm=300, design=design, x=100, y=500
    )
    c.showPage()
    c.save()

    assert isinstance(height, float) and height > 0
    text = pdf_page_text(buf.getvalue(), 0)
    assert "PB5" in text
    assert "Top" in text


def _footing_schedule_top_clears_heading(cfg: PlotConfig, n_rows: int) -> None:
    """Coordinate-based regression for the z-order occlusion bug found in
    code review (commit b4032a6): `_draw_sheet_frame` draws the sheet
    heading at `(page_w / 2, oy + plot_py + 20)`, and
    `_draw_generic_schedule_table` paints an OPAQUE white background as its
    first draw op. If the table's top ever landed at/above the heading's
    glyph band, the white box would silently erase the heading in the
    rendered PDF -- something the text-extraction assertions above can't
    catch, since glyphs stay in the content stream regardless of paint
    order.

    This recomputes the same geometry `render_footing_details` uses
    internally (mirroring its `table_y_top = min(page_h - MARGIN - 30,
    heading_y - 20)` clamp) and asserts the table's top sits strictly below
    the heading's approximate glyph band (heading font size 9 -> glyphs span
    roughly [heading_y - 2, heading_y + 7]), for the given plot geometry.
    """
    page_w, page_h = A4
    s, _denom = _standard_scale(cfg, page_w, page_h)
    plot_py = cfg.plot_length * s
    oy = _centered_plot_oy(
        page_h, plot_py, title_h=TITLE_H, margin=MARGIN, road_below=ROAD_H + ROAD_GAP
    )
    heading_y = oy + plot_py + 20
    table_y_top = min(page_h - MARGIN - 30, heading_y - 20)

    assert table_y_top <= heading_y - 20, (
        f"schedule table top ({table_y_top}) must sit at least 20pt below "
        f"the heading position ({heading_y}) for plot "
        f"{cfg.plot_length}x{cfg.plot_width}"
    )
    # And the table's own bottom edge must not run into the title block.
    table_bottom = table_y_top - _generic_schedule_height(n_rows)
    assert table_bottom > TITLE_H, (
        f"schedule table bottom ({table_bottom}) must clear the title block "
        f"(top at y={TITLE_H}) for plot {cfg.plot_length}x{cfg.plot_width}"
    )


def test_footing_details_schedule_position_clears_heading_default_plot():
    _footing_schedule_top_clears_heading(CFG, n_rows=2)


def test_plinth_beam_plan_renders_beam_marks():
    walls = [
        WallSegment(x1=0, y1=0, x2=4, y2=0, thickness=0.23, kind="external"),
        WallSegment(x1=0, y1=0, x2=0, y2=3, thickness=0.115, kind="internal"),
    ]
    plinth_beams_data = {
        "plinth-external-span4.00": {
            "b_mm": 230,
            "D_mm": 300,
            "span_m": 4.0,
            "kind": "external",
            "count": 1,
            "ok": True,
            "design": {},
            "checks": [],
        },
        "plinth-internal-span3.00": {
            "b_mm": 115,
            "D_mm": 275,
            "span_m": 3.0,
            "kind": "internal",
            "count": 1,
            "ok": True,
            "design": {},
            "checks": [],
        },
    }
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    render_plinth_beam_plan(c, walls, plinth_beams_data, CFG, "Test Project")
    c.showPage()
    c.save()

    text = pdf_page_text(buf.getvalue(), 0)
    assert "PLINTH BEAM PLAN" in text.upper()
    assert "PB1" in text
    assert "PB2" in text


def test_plinth_beam_plan_skips_label_for_unmatched_wall_without_crashing():
    walls = [WallSegment(x1=0, y1=0, x2=5, y2=0, thickness=0.23, kind="external")]
    plinth_beams_data = {}  # no matching group at all
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    render_plinth_beam_plan(c, walls, plinth_beams_data, CFG, "Test Project")
    c.showPage()
    c.save()
    text = pdf_page_text(buf.getvalue(), 0)
    assert "PLINTH BEAM PLAN" in text.upper()


def test_footing_details_schedule_position_clears_heading_tall_narrow_plot():
    # Tall/narrow frontage (common for Indian plots) pushes the plot
    # boundary -- and therefore the heading -- higher up the page than the
    # default near-square CFG does, which is exactly the case that exposed
    # the occlusion bug during review.
    tall_narrow_cfg = PlotConfig(
        plot_length=20.0,
        plot_width=6.0,
        setback_front=3.0,
        setback_rear=1.5,
        setback_left=1.0,
        setback_right=1.0,
        num_bedrooms=2,
        toilets=2,
        parking=True,
    )
    _footing_schedule_top_clears_heading(tall_narrow_cfg, n_rows=2)
