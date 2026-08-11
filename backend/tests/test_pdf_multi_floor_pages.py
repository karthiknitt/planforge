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


def test_g2_plus_basement_has_ten_pages():
    pdf = render_pdf("G+2+B", _stack(sf=True, basement=True), _cfg(), 3)
    assert pdf_pages(pdf) == 10
    assert pdf_page_text(pdf, 8).upper().find("SECTION") != -1
    assert "FRONT ELEVATION" in pdf_page_text(pdf, 9).upper()


def test_arch_page_index_matches_render_order():
    from app.engine.pdf import arch_page_index

    g2 = _stack(sf=True)
    assert arch_page_index(g2, "ground_floor") == 0
    assert arch_page_index(g2, "second_floor") == 2
    both = _stack(sf=True, basement=True)
    assert arch_page_index(both, "basement_floor") == 0
    assert arch_page_index(both, "ground_floor") == 1
    assert arch_page_index(both, "first_floor") == 2
    assert arch_page_index(both, "second_floor") == 3
    assert arch_page_index(both, "unknown_key") == 0  # safe fallback


def test_stair_label_is_floor_aware():
    from tests.helpers.pdf_png import pdf_page_text

    pdf = render_pdf("G+1", _stack(), _cfg(), 3)
    assert "UP" in pdf_page_text(pdf, 0)  # ground floor: floor exists above
    assert "DN" in pdf_page_text(pdf, 1)  # first (top) floor


def test_stair_tread_geometry_east_west():
    from app.engine.pdf import _stair_tread_elements

    room = _room("stair", "staircase", 5.13, 1.73, 4.0, 2.0)  # wider than deep
    el = _stair_tread_elements(room)
    # indicator + treads + break line all run VERTICALLY for an E-W flight:
    for x1, y1, x2, y2 in [el["indicator"], *el["treads"], el["break_line"]]:
        assert x1 == x2 and y1 != y2
    assert el["arrow"][0] != el["arrow"][2]  # arrow advances along x
    assert el["arrow"][1] == el["arrow"][3]


def test_stair_tread_geometry_square_room_picks_vertical():
    from app.engine.pdf import _stair_tread_elements

    room = _room("sq", "staircase", 5.13, 1.73, 3.0, 3.0)  # depth == width
    el = _stair_tread_elements(room)
    # tie-break parity with plan_geometry.derive_stair: vertical (S->N) branch wins
    for x1, y1, x2, y2 in [el["indicator"], *el["treads"], el["break_line"]]:
        assert y1 == y2 and x1 != x2  # horizontal segments
    assert el["arrow"][0] == el["arrow"][2]  # arrow stem vertical (constant x)


def test_stair_tread_depth_defaults_to_vertical_standards():
    # CodeRabbit: tread depth must flow from the engine's canonical vertical
    # standards, not a hardcoded 270mm literal inside the renderer.
    import inspect

    from app.engine.pdf import _stair_tread_elements
    from app.engine.vertical_standards import VS

    sig = inspect.signature(_stair_tread_elements)
    assert sig.parameters["tread_m"].default == VS.stair_tread_m


def test_stair_tread_count_reacts_to_tread_depth():
    # the parameter is actually USED: a 4m-deep stair gets fewer treads with
    # 500mm treads than with 250mm treads
    from app.engine.pdf import _stair_tread_elements

    room = _room("stair", "staircase", 5.13, 1.73, 2.0, 4.0)  # deeper than wide
    coarse = _stair_tread_elements(room, tread_m=0.5)
    fine = _stair_tread_elements(room, tread_m=0.25)
    assert len(coarse["treads"]) != len(fine["treads"])


def test_new_room_types_render():
    # non-overlapping tiling of the _cfg plate (x 1.13..10.33, y 1.73..13.23)
    gf = [
        _room("foyer", "foyer", 1.13, 1.73, 2.5, 3.0),
        _room("court", "courtyard", 3.63, 1.73, 1.5, 3.0),
        _room("stair", "staircase", 5.13, 1.73, 2.0, 5.0),
        _room("ww", "wardrobe", 7.13, 1.73, 2.0, 2.0),
        _room("bed", "bedroom", 7.13, 3.73, 2.5, 3.0),
        _room("living", "living", 1.13, 4.73, 4.0, 4.0),
    ]
    pdf = render_pdf("NewTypes", _make_layout(gf, ff_rooms=[]), _cfg(), 3)
    assert pdf_pages(pdf) == 6
