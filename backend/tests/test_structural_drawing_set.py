from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.engine.cad_elements import ColumnMarker, WallSegment
from app.engine.models import PlotConfig
from app.engine.structural_drawing_set import render_column_footing_plan
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
