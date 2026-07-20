"""Wall-UDL load takedown for plinth beam design.

Plinth beams in ordinary Indian G+1 residential construction carry no slab
reaction (ground floor rests on filled/compacted earth, not a suspended
slab) -- they carry the masonry wall dead load above them plus self-weight.
IS 456 has no distinct "plinth beam" clause; this is an ordinary beam sized
against this load via structapi's generic beam-design API, not the
slab-driven design chain used for roof beams.

Wall height uses compliance_rules.json's min_habitable_ceiling_m as a proxy
for full storey height -- there is no dedicated plinth/floor-to-floor height
key in compliance_rules.json (documented simplification, see
docs/plans/2026-07-19-structural-drawing-set-design.md #2).
"""

from __future__ import annotations

#: IS 875 Part 1 unit weight, brick masonry (kN/m3) -- matches
#: structapi's iscodes/tables.py UNIT_WEIGHTS["brick_masonry"].
BRICK_MASONRY_UNIT_WEIGHT_KN_M3 = 20.0


def wall_udl_kn_m(
    thickness_mm: float,
    height_m: float,
    unit_weight_kn_m3: float = BRICK_MASONRY_UNIT_WEIGHT_KN_M3,
) -> float:
    """Dead-load UDL (kN/m run) a masonry wall imposes on the beam below it."""
    return (thickness_mm / 1000.0) * height_m * unit_weight_kn_m3
