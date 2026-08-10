"""Page emission for G+2 / basement layouts (solver_limitations #6a)."""

from app.engine.pdf import render_pdf

from tests.helpers.pdf_png import pdf_page_text, pdf_pages
from tests.test_multi_floor import _cfg, _make_layout, _room


def _stack(sf=False, basement=False):
    gf = [
        _room("living", "living", 1.13, 1.73, 4.0, 5.0),
        _room("stair", "staircase", 5.13, 1.73, 2.0, 5.0),
        _room("bed", "bedroom", 7.13, 1.73, 2.84, 5.0),
    ]
    ff = [  # same footprint — free column-grid cross-check
        _room("bed1", "bedroom", 1.13, 1.73, 4.0, 5.0),
        _room("stair1", "staircase", 5.13, 1.73, 2.0, 5.0),
        _room("bed2", "bedroom", 7.13, 1.73, 2.84, 5.0),
    ]
    sf_rooms = [
        _room("bed3", "bedroom", 1.13, 1.73, 4.0, 5.0),
        _room("stair2", "staircase", 5.13, 1.73, 2.0, 5.0),
        _room("bed4", "bedroom", 7.13, 1.73, 2.84, 5.0),
    ]
    basement_rooms = [_room("hall", "gym", 1.13, 1.73, 8.84, 5.0)]
    return _make_layout(
        gf_rooms=gf,
        ff_rooms=ff,
        sf_rooms=sf_rooms if sf else None,
        basement_rooms=basement_rooms if basement else None,
    )


def test_g2_pdf_has_second_floor_pages():
    pdf = render_pdf("G+2", _stack(sf=True), _cfg(), 3)
    assert pdf_pages(pdf) == 8  # SF-arch + SF-structural in addition to 6
    assert "SECOND FLOOR" in pdf_page_text(pdf, 2).upper()  # SF architectural
    assert "SECOND FLOOR" in pdf_page_text(pdf, 5).upper()  # SF structural


def test_g1_basement_pdf_has_basement_pages():
    pdf = render_pdf("G+1+Basement", _stack(basement=True), _cfg(), 3)
    assert pdf_pages(pdf) == 8
    assert "BASEMENT" in pdf_page_text(pdf, 0).upper()  # basement architectural
    assert "BASEMENT" in pdf_page_text(pdf, 3).upper()  # basement structural


def test_g1_still_six_pages():  # regression guard — existing behaviour unchanged
    pdf = render_pdf("G+1", _stack(), _cfg(), 3)
    assert pdf_pages(pdf) == 6
