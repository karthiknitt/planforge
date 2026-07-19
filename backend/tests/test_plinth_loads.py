import pytest

from app.engine.plinth_loads import wall_udl_kn_m


def test_wall_udl_external_wall():
    # 230mm external wall, 2.75m ceiling height, brick masonry (20 kN/m3)
    # udl = thickness_m * height_m * unit_weight_kn_m3
    #     = 0.230 * 2.75 * 20.0 = 12.65 kN/m
    udl = wall_udl_kn_m(thickness_mm=230, height_m=2.75)
    assert udl == pytest.approx(12.65, abs=0.01)


def test_wall_udl_internal_wall_lighter():
    udl_ext = wall_udl_kn_m(thickness_mm=230, height_m=2.75)
    udl_int = wall_udl_kn_m(thickness_mm=115, height_m=2.75)
    assert udl_int < udl_ext
    assert udl_int == pytest.approx(6.325, abs=0.01)
