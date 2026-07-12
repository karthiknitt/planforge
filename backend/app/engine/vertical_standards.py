from dataclasses import dataclass


@dataclass(frozen=True)
class VerticalStandards:
    floor_to_floor_m: float = 3.0
    slab_t_m: float = 0.15
    plinth_h_m: float = 0.45
    foundation_depth_m: float = 0.9
    footing_w_m: float = 0.75
    footing_t_m: float = 0.3
    sill_h_m: float = 0.9
    lintel_h_m: float = 2.1
    lintel_t_m: float = 0.15
    door_h_m: float = 2.1
    vent_sill_m: float = 1.5
    chajja_proj_m: float = 0.45
    chajja_t_m: float = 0.1
    parapet_h_m: float = 1.0
    parapet_t_m: float = 0.23
    stair_riser_m: float = 0.175
    stair_tread_m: float = 0.25
    waist_t_m: float = 0.15


VS = VerticalStandards()


def fmt_level(z: float) -> str:
    if abs(z) < 0.005:
        return "±0.00"
    return f"{z:+.3f}"
