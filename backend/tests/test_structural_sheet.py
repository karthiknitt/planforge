"""Foundation tests for the Structural Drawing Set (`structural_sheet.py`).

The registration test below is the point of the whole module: sheets in a
drawing set must overlay. The renderer this set replaces computed its scale
with a reserved schedule column on some sheets and without it on others, so
two plans of the same building were drawn at different scales and origins.
Nothing in a text-extraction test can see that, which is exactly why it
survived — so it is pinned numerically here.
"""

from io import BytesIO

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.engine.models import PlotConfig
from app.engine.structural_sheet import (
    DETAIL_DENOMS,
    SHEET_REGISTER,
    SHEET_TITLES,
    LabelPlacer,
    detail_scale,
    detail_sheet_frame,
    fit_detail_scale,
    grid_letter,
    paginate_boxes,
    plan_sheet_frame,
    structural_title_block,
)
from tests.helpers.pdf_png import pdf_page_text

CFG = PlotConfig(
    plot_x_extent=12.192,
    plot_y_extent=18.288,
    num_bedrooms=2,
    toilets=2,
    setback_front=1.5,
    setback_rear=1.5,
    setback_left=1.2,
    setback_right=1.2,
    parking=True,
    city="other",
    road_side="E",
)

# A deliberately awkward second plot: narrow and long, so it lands on a
# different standard scale denominator than CFG and the registration
# assertion is not accidentally true for one geometry only.
NARROW_CFG = PlotConfig(
    plot_x_extent=6.1,
    plot_y_extent=9.15,
    num_bedrooms=2,
    toilets=1,
    setback_front=1.5,
    setback_rear=1.0,
    setback_left=0.9,
    setback_right=0.9,
    parking=False,
    city="other",
    road_side="S",
)


def _canvas() -> tuple[canvas.Canvas, BytesIO]:
    buf = BytesIO()
    return canvas.Canvas(buf, pagesize=A4), buf


# ── registration ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("cfg", [CFG, NARROW_CFG], ids=["wide", "narrow"])
def test_all_plan_sheets_share_one_frame(cfg):
    """S-02, S-05, S-07 and S-09 are separate calls on separate sheets; they
    must project model coordinates identically — same origin, same scale,
    same denominator.

    If this fails the sheets cannot be overlaid, traced or checked against
    each other, which is the whole reason a set exists. The renderer this
    replaces computed the scale with a reserved schedule column on some
    sheets and without it on others, so two plans of the same building came
    out at different scales AND origins. Asserted on two plot geometries that
    land on different standard denominators, so it cannot pass by coincidence
    on one shape.
    """
    frames = []
    for drg in ("S-02", "S-05", "S-07", "S-09"):
        c, _ = _canvas()
        frames.append(
            plan_sheet_frame(c, cfg, heading=SHEET_TITLES[drg], drg_no=drg).as_tuple()
        )
    assert len(set(frames)) == 1, f"plan sheets drawn at differing frames: {frames}"


def test_plan_sheets_are_not_scale_starved_by_a_schedule_column():
    """Withholding a 160 pt schedule column costs a full standard scale step
    on an ordinary Indian plot — 1:200 instead of 1:100 — while a third of
    the page height goes unused. 1:200 is too small to set out a foundation
    from, so schedules overlay the drawing instead of sitting beside it.
    """
    c, _ = _canvas()
    frame = plan_sheet_frame(c, CFG, heading=SHEET_TITLES["S-02"], drg_no="S-02")
    assert frame.denom <= 100, (
        f"12.19 x 18.29 m plot drawn at 1:{frame.denom} — a residential "
        "foundation plan must reach 1:100 on A4"
    )
    # and it genuinely fits the page, rather than merely claiming a scale
    assert frame.plot_px <= A4[0] - 2 * 52
    assert frame.oy + frame.plot_py <= A4[1] - 52


# ── sheet register ───────────────────────────────────────────────────────────


def test_sheet_register_is_twelve_unique_numbered_sheets():
    numbers = [n for n, _ in SHEET_REGISTER]
    assert len(SHEET_REGISTER) == 12
    assert numbers == sorted(numbers)
    assert len(set(numbers)) == 12
    assert numbers[0] == "S-01" and numbers[-1] == "S-12"
    assert all(title.strip() for _, title in SHEET_REGISTER)


# ── detail scales ────────────────────────────────────────────────────────────


def test_detail_scale_returns_a_standard_denominator_that_fits():
    px_per_mm, denom = detail_scale(1200.0, 400.0)
    assert denom in DETAIL_DENOMS
    assert 1200.0 * px_per_mm <= 400.0


def test_detail_scale_prefers_the_largest_scale_that_fits():
    """Finer denominators come first, so a detail is drawn as large as the
    space honestly allows rather than shrunk to a fixed constant."""
    _, tight = detail_scale(1200.0, 120.0)
    _, roomy = detail_scale(1200.0, 400.0)
    assert roomy < tight, "more space should yield a finer (smaller-N) scale"


def test_detail_scale_falls_back_rather_than_overflowing_silently():
    px_per_mm, denom = detail_scale(50_000.0, 100.0)
    assert denom == DETAIL_DENOMS[-1]
    assert px_per_mm > 0


def test_fit_detail_scale_respects_both_axes():
    px_per_mm, denom = fit_detail_scale(1200.0, 900.0, 400.0, 60.0)
    assert 900.0 * px_per_mm <= 60.0 or denom == DETAIL_DENOMS[-1]


def test_detail_scale_handles_degenerate_input():
    assert detail_scale(0.0, 400.0)[1] == DETAIL_DENOMS[-1]
    assert detail_scale(1200.0, 0.0)[1] == DETAIL_DENOMS[-1]


# ── pagination ───────────────────────────────────────────────────────────────


def test_paginate_boxes_never_drops_an_item():
    items = list(range(25))
    pages = paginate_boxes(items, lambda _i: 100.0, top=600.0, bottom=100.0, gap=10.0)
    assert [i for page in pages for i in page] == items


def test_paginate_boxes_respects_the_bottom_bound():
    pages = paginate_boxes(
        list(range(10)), lambda _i: 100.0, top=600.0, bottom=100.0, gap=10.0
    )
    for page in pages:
        assert 100.0 * len(page) <= 600.0 - 100.0 + 10.0 * len(page)


def test_paginate_boxes_gives_an_oversized_item_its_own_page():
    """An item taller than a page must still be drawn. The renderer this
    replaces used a `break`, which silently truncated the beam-detail list —
    on a construction drawing, a dropped beam is an unbuilt beam."""
    pages = paginate_boxes(
        ["huge", "small"],
        lambda i: 5000.0 if i == "huge" else 50.0,
        top=600.0,
        bottom=100.0,
        gap=10.0,
    )
    assert [i for page in pages for i in page] == ["huge", "small"]
    assert len(pages) == 2


def test_paginate_boxes_on_empty_input():
    assert paginate_boxes([], lambda _i: 10.0, top=600.0, bottom=100.0) == []


# ── label de-collision ───────────────────────────────────────────────────────


def test_label_placer_moves_a_colliding_label_to_its_alternate():
    lp = LabelPlacer(dx=16.0, dy=7.0)
    assert lp.place([(100.0, 100.0)]) == (100.0, 100.0)
    assert lp.place([(102.0, 101.0), (300.0, 300.0)]) == (300.0, 300.0)
    assert lp.collisions == 0


def test_label_placer_still_places_when_every_candidate_collides():
    lp = LabelPlacer()
    lp.place([(100.0, 100.0)])
    placed = lp.place([(101.0, 100.0), (102.0, 101.0)])
    assert placed == (101.0, 100.0)
    assert lp.collisions == 1, "unresolved collisions must be counted, not hidden"


def test_label_placer_rejects_no_candidates():
    with pytest.raises(ValueError):
        LabelPlacer().place([])


# ── grid letters ─────────────────────────────────────────────────────────────


def test_grid_letters_continue_past_z():
    assert [grid_letter(i) for i in (0, 1, 25, 26, 27)] == ["A", "B", "Z", "AA", "AB"]


# ── frames + title block ─────────────────────────────────────────────────────


def test_detail_frame_carries_no_plot_furniture_and_marks_continuations():
    c, buf = _canvas()
    frame = detail_sheet_frame(c, heading="FOOTING DETAILS", drg_no="S-03")
    structural_title_block(
        c,
        project_name="MyLatest",
        cfg=CFG,
        drg_no="S-03",
        sheet_title="FOOTING DETAILS",
        page_w=A4[0],
        scale_text="AS SHOWN",
    )
    c.showPage()
    detail_sheet_frame(c, heading="FOOTING DETAILS", drg_no="S-03", continued=True)
    c.showPage()
    c.save()

    assert frame.width > 0 and frame.height > 0
    first = pdf_page_text(buf.getvalue(), 0)
    assert "FOOTING DETAILS" in first
    assert "S-03" in first
    # the road strip label belongs on plan sheets only
    assert "ROAD" not in first
    assert "CONTD" in pdf_page_text(buf.getvalue(), 1)


def test_structural_title_block_omits_the_meaningless_bhk_field():
    """The architectural title block prints an "N BHK" CONFIG cell. Structural
    callers could only satisfy it with 0, printing "0 BHK" on every sheet."""
    c, buf = _canvas()
    structural_title_block(
        c,
        project_name="MyLatest",
        cfg=CFG,
        drg_no="S-04",
        sheet_title="COLUMN DETAILS & SCHEDULE",
        page_w=A4[0],
        scale_denom=25,
        revision="B",
    )
    c.showPage()
    c.save()

    text = pdf_page_text(buf.getvalue(), 0)
    assert "BHK" not in text
    assert "S-04" in text
    assert "1:25" in text
    assert "B" in text


def test_plan_sheet_frame_draws_road_and_drawing_number():
    c, buf = _canvas()
    plan_sheet_frame(c, CFG, heading=SHEET_TITLES["S-02"], drg_no="S-02")
    c.showPage()
    c.save()

    text = pdf_page_text(buf.getvalue(), 0)
    assert "COLUMN & FOOTING PLAN" in text
    assert "ROAD" in text
    assert "S-02" in text
