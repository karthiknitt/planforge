"""Smoke tests for the shared render/test helpers used by the CAD-quality work."""

from app.engine.pdf import render_pdf

from tests.helpers.golden import golden_config, golden_layout
from tests.helpers.pdf_png import (
    mean_saturation,
    pdf_page_text,
    pdf_pages,
    render_page_png,
)


def _standard_pdf() -> bytes:
    cfg = golden_config()
    layout = golden_layout()
    return render_pdf("Golden Fixture", layout, cfg, cfg.num_bedrooms)


def test_golden_fixture_is_deterministic():
    a = golden_layout()
    b = golden_layout()
    assert [r.id for r in a.ground_floor.rooms] == [r.id for r in b.ground_floor.rooms]
    assert golden_config().plot_width == 9.0


def test_pdf_pages_and_text():
    pdf = _standard_pdf()
    assert pdf_pages(pdf) >= 2
    assert "GROUND FLOOR" in pdf_page_text(pdf, 0).upper()


def test_render_page_png():
    png = render_page_png(_standard_pdf(), 0)
    assert png.startswith(b"\x89PNG")


def test_mean_saturation_is_low_for_line_drawing():
    png = render_page_png(_standard_pdf(), 0)
    assert 0.0 <= mean_saturation(png) < 0.2
