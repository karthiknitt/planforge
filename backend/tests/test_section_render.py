from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.engine.generator import generate
from app.engine.models import PlotConfig
from app.engine.section_geometry import derive_elevation, derive_section
from app.engine.section_render import render_elevation_view, render_section_view
from app.quality.pdf_image import pdf_page_png

from tests.helpers.pdf_png import mean_saturation

CFG = PlotConfig(
    plot_y_extent=12.0,
    plot_x_extent=9.0,
    setback_front=3.0,
    setback_rear=1.5,
    setback_left=1.0,
    setback_right=1.0,
    num_bedrooms=2,
    toilets=2,
    parking=True,
)


def _one_page_pdf(draw) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw(c)
    c.showPage()
    c.save()
    return buf.getvalue()


def test_section_view_renders_monochrome():
    lay = generate(CFG)[0]
    sd = derive_section(lay, CFG)
    pdf = _one_page_pdf(lambda c: render_section_view(c, sd, (40, 120, 515, 620)))
    png = pdf_page_png(pdf, 0)
    assert mean_saturation(png) < 0.02


def test_elevation_view_renders():
    lay = generate(CFG)[0]
    ed = derive_elevation(lay, CFG)
    pdf = _one_page_pdf(lambda c: render_elevation_view(c, ed, (40, 120, 515, 620)))
    assert pdf[:4] == b"%PDF"
