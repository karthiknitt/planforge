"""Composition invariants for the PDF page layout (Bug #8).

Plots must be vertically centred (not bottom-anchored) on every plan and
structural page, and the AREA / OPENINGS schedule tables must live in a
reserved bottom-right column that never overlaps the plot for any aspect
ratio. These are checked via the pure layout helpers (deterministic, no image
diffing) plus a smoke render of both PDFs from the frozen golden fixture.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from reportlab.lib.pagesizes import A4

from app.engine.approval_pdf import OwnerInfo, generate_approval_pdf
from app.engine.cad_elements import Opening
from app.engine.models import PlotConfig
from app.engine.pdf import (
    MARGIN,
    ROAD_GAP,
    ROAD_H,
    SCHED_PAD,
    SCHED_RESERVE,
    SCHED_W,
    TITLE_H,
    _area_schedule_height,
    _centered_plot_oy,
    _openings_schedule_height,
    _openings_schedule_rows,
    _schedule_column_x,
    _standard_scale,
    render_pdf,
)

from tests.helpers.golden import golden_config, golden_layout
from tests.helpers.pdf_png import pdf_page_text, pdf_pages

PAGE_W, PAGE_H = A4

_OWNER = OwnerInfo(
    owner_name="Test Owner",
    survey_number="123/4",
    locality="Trichy",
    engineer_name="Er. Test",
    license_number="LIC-1",
    municipality="Chennai",
)

# A spread of plot shapes: square, wide, tall, extreme aspect ratios.
_ASPECTS = [
    (9.0, 9.0),
    (18.0, 6.0),
    (6.0, 18.0),
    (30.0, 6.0),
    (6.0, 30.0),
    (12.0, 15.0),
]


def _cfg(width: float, length: float) -> PlotConfig:
    return PlotConfig(
        plot_y_extent=length,
        plot_x_extent=width,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=1.0,
        setback_right=1.0,
        num_bedrooms=2,
        toilets=2,
        parking=True,
    )


# ── Pure helper: vertical centring ───────────────────────────────────────────


@pytest.mark.parametrize(("width", "length"), _ASPECTS)
def test_plot_group_is_vertically_centered(width: float, length: float) -> None:
    """The plot+road group has equal slack above and below (centred, not
    bottom-anchored)."""
    cfg = _cfg(width, length)
    s, _ = _standard_scale(cfg, PAGE_W, PAGE_H, reserve_w=SCHED_RESERVE)
    plot_py = cfg.plot_y_extent * s
    road_below = ROAD_H + ROAD_GAP
    oy = _centered_plot_oy(
        PAGE_H, plot_py, title_h=TITLE_H, margin=MARGIN, road_below=road_below
    )

    gap_below = (oy - road_below) - TITLE_H
    gap_above = (PAGE_H - MARGIN) - (oy + plot_py)
    assert gap_below == pytest.approx(gap_above, abs=0.5)
    assert gap_below > 0  # not glued to the title block


def test_centering_accounts_for_road_above() -> None:
    """When the road sits above the plot (north road), the group still centres
    as a unit."""
    plot_py = 300.0
    road_above = ROAD_H + ROAD_GAP
    oy = _centered_plot_oy(
        PAGE_H, plot_py, title_h=TITLE_H, margin=MARGIN, road_above=road_above
    )
    gap_below = oy - TITLE_H
    gap_above = (PAGE_H - MARGIN) - (oy + plot_py + road_above)
    assert gap_below == pytest.approx(gap_above, abs=0.5)


# ── Pure helper: schedule column never overlaps the plot ─────────────────────


@pytest.mark.parametrize(("width", "length"), _ASPECTS)
def test_schedule_column_clear_of_plot(width: float, length: float) -> None:
    cfg = _cfg(width, length)
    s, _ = _standard_scale(cfg, PAGE_W, PAGE_H, reserve_w=SCHED_RESERVE)
    plot_px = cfg.plot_x_extent * s
    ox = MARGIN + (PAGE_W - 2 * MARGIN - SCHED_RESERVE - plot_px) / 2
    sched_x = _schedule_column_x(PAGE_W, MARGIN)

    # Plot right edge stays left of the schedule column, with the pad gap.
    assert ox + plot_px <= sched_x - SCHED_PAD + 1e-6
    # The schedule column is exactly SCHED_W wide inside the right margin.
    assert sched_x + SCHED_W == pytest.approx(PAGE_W - MARGIN)


def test_schedule_tables_sit_above_title_block_not_top_corner() -> None:
    """Tables anchor just above the title block (bottom half), not the old
    top-of-page corners."""
    fp = golden_layout().ground_floor
    area_h = _area_schedule_height(fp)
    area_top = TITLE_H + SCHED_PAD + area_h
    # The whole area table lives in the lower half of the page.
    assert area_top < PAGE_H / 2
    # Its bottom edge clears the title block.
    assert area_top - area_h >= TITLE_H


def test_schedule_rows_survive_legacy_openings_with_empty_marks() -> None:
    """Hand-built openings default `mark` to "" and never went through
    `assign_opening_marks`. `_mark_order` used to call `int(mark[1:])` on that
    empty string and crash — CodeRabbit finding on PR #96. Schedule generation
    must instead assign canonical marks on the fly, not crash."""
    door = Opening(
        kind="door", cx=1.0, cy=0.0, width=0.9, is_horizontal=True, wall_thickness=0.115
    )
    window = Opening(
        kind="window",
        cx=3.0,
        cy=0.0,
        width=1.2,
        is_horizontal=True,
        wall_thickness=0.23,
    )
    drawing = SimpleNamespace(openings=[door, window])
    rows = _openings_schedule_rows(drawing)
    assert {row[1] for row in rows} == {"DOOR", "WINDOW"}
    assert door.mark and window.mark, "legacy openings must get real marks assigned"


def test_schedule_height_helpers_match_row_math() -> None:
    fp = golden_layout().ground_floor
    # band(11) + row(9) * (rooms + 2)
    assert _area_schedule_height(fp) == pytest.approx(11.0 + 9.0 * (len(fp.rooms) + 2))
    rows = [("D1", "DOOR", 900, 2100, 3), ("W1", "WINDOW", 1200, 1200, 4)]
    assert _openings_schedule_height(rows) == pytest.approx(11.0 + 9.0 * (2 + 1))


# ── Smoke render: both PDFs still produce correct pages + shared title block ──


def test_standard_pdf_renders_with_schedule_and_shared_title_block() -> None:
    pdf = render_pdf("Test Project", golden_layout(), golden_config(), 3)
    assert pdf_pages(pdf) == 6
    gf_text = pdf_page_text(pdf, 0).upper()
    assert "AREA SCHEDULE" in gf_text
    assert "SCHEDULE OF OPENINGS" in gf_text
    # Shared title-block field labels present.
    for label in ("PROJECT", "LAYOUT", "SCALE", "TOTAL AREA"):
        assert label in gf_text


def test_approval_pdf_renders_with_shared_title_block_and_signature() -> None:
    pdf = generate_approval_pdf(golden_layout(), golden_config(), _OWNER, "A")
    assert pdf_pages(pdf) == 5
    gf_text = pdf_page_text(pdf, 1).upper()
    assert "AREA SCHEDULE" in gf_text
    assert "AUTHORITY" in gf_text  # shared field label
    # Submission (section) page carries the unified signature/seal strip.
    section_text = pdf_page_text(pdf, 3).upper()
    assert "AUTHORISED SIGNATORY" in section_text
    assert "SEAL" in section_text
