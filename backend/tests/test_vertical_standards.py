from app.engine.vertical_standards import VS, fmt_level


def test_defaults_match_indian_conventions():
    assert VS.floor_to_floor_m == 3.0
    assert VS.slab_t_m == 0.15
    assert VS.plinth_h_m == 0.45
    assert VS.foundation_depth_m == 0.9
    assert VS.sill_h_m == 0.9
    assert VS.lintel_h_m == 2.1
    assert VS.door_h_m == 2.1
    assert VS.parapet_h_m == 1.0
    assert VS.stair_riser_m == 0.175
    assert VS.stair_tread_m == 0.25


def test_fmt_level():
    assert fmt_level(0.0) == "±0.00"
    assert fmt_level(3.0) == "+3.000"
    assert fmt_level(-0.45) == "-0.450"
