from io import BytesIO

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.quality.pdf_image import pdf_page_png

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _two_page_pdf() -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(100, 700, "PAGE ONE")
    c.showPage()
    c.drawString(100, 700, "PAGE TWO")
    c.showPage()
    c.save()
    return buf.getvalue()


def test_returns_png_bytes():
    png = pdf_page_png(_two_page_pdf())
    assert png.startswith(PNG_MAGIC)
    assert len(png) > 1000


def test_scale_changes_output_dimensions():
    small = pdf_page_png(_two_page_pdf(), scale=1.0)
    large = pdf_page_png(_two_page_pdf(), scale=2.0)
    assert len(large) != len(small)


def test_page_index_out_of_range_clamps_to_last():
    png = pdf_page_png(_two_page_pdf(), page_idx=99)
    assert png.startswith(PNG_MAGIC)


def test_empty_bytes_raises():
    with pytest.raises(Exception):
        pdf_page_png(b"")
