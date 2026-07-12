from app.engine.approval_pdf import OwnerInfo, generate_approval_pdf
from app.engine.generator import generate
from app.engine.models import PlotConfig

from tests.helpers.pdf_png import pdf_page_text, pdf_pages

CFG = PlotConfig(
    plot_length=12.0,
    plot_width=9.0,
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
    owner = OwnerInfo(
        owner_name="Test Owner",
        survey_number="123/4",
        locality="Trichy",
        engineer_name="Er. Test",
        license_number="LIC-1",
        municipality="Trichy Corp",
    )
    return generate_approval_pdf(lay, CFG, owner, "A")


def test_approval_pdf_has_five_pages():
    assert pdf_pages(_pdf()) == 5


def test_approval_section_page_is_convention_faithful():
    text = pdf_page_text(_pdf(), 3)
    assert "SECTION A-A" in text.upper()
    assert "±0.00" in text


def test_approval_elevation_page():
    text = pdf_page_text(_pdf(), 4).upper()
    assert "FRONT ELEVATION" in text
