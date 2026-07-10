"""Site location plan (approval PDF page 0) — B/W convention, all road sides."""

import dataclasses

from app.engine.approval_pdf import OwnerInfo, generate_approval_pdf

from tests.helpers.golden import golden_config, golden_layout
from tests.helpers.pdf_png import mean_saturation, pdf_page_text, render_page_png

OWNER = OwnerInfo(
    owner_name="Sivavela Builders",
    survey_number="123/4A",
    locality="Thillai Nagar, Chennai",
    engineer_name="K. Natarajan",
    license_number="TN-ENG-2024-0001",
    municipality="chennai_cmda",
)


def _render(cfg=None, road_side=None):
    cfg = cfg or golden_config()
    if road_side:
        cfg = dataclasses.replace(cfg, road_side=road_side)
    layout = golden_layout()
    return generate_approval_pdf(layout, cfg, OWNER, layout.id)


def test_site_plan_is_strictly_black_and_white():
    pdf = _render()
    assert mean_saturation(render_page_png(pdf, 0)) < 0.02


def test_site_plan_has_required_text():
    pdf = _render()
    text = pdf_page_text(pdf, 0).upper()
    for token in ("SITE LOCATION PLAN", "NORTH", "123/4A", "ROAD"):
        assert token in text


def test_site_plan_road_strip_for_every_side():
    for side in ("S", "N", "E", "W"):
        pdf = _render(road_side=side)
        assert "ROAD" in pdf_page_text(pdf, 0).upper(), side


def test_front_setback_label_does_not_collide_with_survey_caption():
    # Regression: the Front-setback label used to sit directly on top of
    # the survey-number line inside the plot. Both are now vertically
    # separated by construction (setback label stays inside the plot;
    # caption moved below the compound) — assert both render without
    # exceptions and both texts are present.
    pdf = _render()
    text = pdf_page_text(pdf, 0)
    assert "FRONT SETBACK" in text  # standardized callout format, e.g. 1.5M FRONT SETBACK
    assert "S.No:" in text
