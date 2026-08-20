from app.engine.generator import generate
from app.engine.models import PlotConfig
from app.engine.pdf import render_pdf

from tests.helpers.pdf_png import pdf_page_text, pdf_pages

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


def _pdf() -> bytes:
    lay = generate(CFG)[0]
    return render_pdf("Test Project", lay, CFG, 2)


def test_standard_pdf_has_six_pages():
    assert pdf_pages(_pdf()) == 6


def test_section_page_content():
    text = pdf_page_text(_pdf(), 4).upper()
    assert "SECTION A-A" in text
    assert "SCALE" in text


def test_elevation_page_content():
    text = pdf_page_text(_pdf(), 5).upper()
    assert "FRONT ELEVATION" in text
    assert "SCALE" in text
