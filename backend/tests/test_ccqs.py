"""CCQS deterministic scorer — synthetic PDFs built in-test with reportlab."""

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.quality.ccqs import CcqsResult, compute_ccqs_deterministic


def _mono_pdf_with_text(lines: list[str]) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFillColorRGB(0, 0, 0)
    y = 800
    for line in lines:
        c.drawString(50, y, line)
        y -= 20
    c.showPage()
    c.save()
    return buf.getvalue()


def _color_pdf() -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFillColorRGB(1, 0, 0)
    c.rect(0, 0, 595, 842, fill=1, stroke=0)
    c.showPage()
    c.save()
    return buf.getvalue()


FULL_MARKS_LINES = [
    # 10 dimension strings => dimension_density 20
    *[f"{n}'-6\"" for n in range(3, 13)],
    # the same lines are ft-in patterns (>=5 => ft_in_labels 20)
    "GROUND FLOOR PLAN",
    "FIRST FLOOR PLAN",
    "AREA STATEMENT",
    "ROOM AREA SQFT",
    "TOTAL AREA 1450 SQFT",
    "NORTH",
]


def test_full_marks_mono_pdf_scores_80():
    pdf = _mono_pdf_with_text(FULL_MARKS_LINES)
    result = compute_ccqs_deterministic(pdf)
    assert isinstance(result, CcqsResult)
    assert result.monochrome == 20.0
    assert result.dimension_density == 20.0
    assert result.ft_in_labels == 20.0
    assert result.layout_completeness == 20.0
    assert result.total == 80.0


def test_color_pdf_loses_monochrome_points():
    result = compute_ccqs_deterministic(_color_pdf())
    assert result.monochrome < 15.0


def test_sparse_pdf_scores_low():
    result = compute_ccqs_deterministic(_mono_pdf_with_text(["hello"]))
    assert result.dimension_density == 0.0
    assert result.ft_in_labels == 0.0
    assert result.layout_completeness == 0.0


def test_metric_dimensions_count_toward_density():
    pdf = _mono_pdf_with_text(["3.50 m", "4.25 m", "2.10 m"])
    result = compute_ccqs_deterministic(pdf)
    assert result.dimension_density == 6.0  # 3 dims x 2.0


def test_as_dict_shape():
    d = compute_ccqs_deterministic(_mono_pdf_with_text(["x"])).as_dict()
    assert set(d) == {
        "total",
        "max",
        "monochrome",
        "dimension_density",
        "ft_in_labels",
        "layout_completeness",
    }
    assert d["max"] == 80
