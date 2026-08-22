"""Canonical furniture fixtures (Phase 7 / Task 33).

Ported VERBATIM from cad_advanced's twelve ``_furniture_*`` renderers — the
richer of the two pre-existing implementations (DXF + frontend SVG) and the
plan's designated specification. What changed: each function is a pure
emitter returning room-relative `Fixture` entities instead of an ezdxf
immediate-mode draw, so the PDF, the DXF exporter and the SVG frontend all
project ONE derivation.

Porting rules (and the DXF projector in cad_advanced mirrors them back):
- every coordinate is room-relative — the original ``room.x``/``room.y``
  offsets are dropped, nothing else changes;
- emission ORDER within a room is preserved exactly (golden-pinned);
- each original ezdxf call becomes one FixtureShape:
  ``_rect`` → rect (closed), ``add_lwpolyline(..., DASHED)`` → rect with
  dashed=True, ``add_circle`` → circle, ``add_arc`` → arc, ``add_line`` →
  line.
"""

from __future__ import annotations

from app.engine.cad_elements import Fixture, FixtureShape
from app.engine.models import Room

# ── Bedroom / Master Bedroom ─────────────────────────────────────────────────


def _bedroom(room: Room) -> list[Fixture]:
    """Bed with headboard against the rear wall; side table circle right."""
    margin = 0.15
    is_master = room.type == "master_bedroom"
    bed_w = min(1.8 if is_master else 1.2, room.width - 2 * margin)
    bed_d = min(2.0, room.depth - margin)
    if bed_w < 0.5 or bed_d < 0.5:
        return []

    bx = (room.width - bed_w) / 2
    by = room.depth - margin - bed_d  # headboard at the top
    fixtures = [
        Fixture(
            kind="bed",
            room_id=room.id,
            shapes=[
                FixtureShape(kind="rect", x=bx, y=by, width=bed_w, depth=bed_d),
                # Headboard bar (10 cm strip at the top of bed)
                FixtureShape(
                    kind="rect", x=bx, y=by + bed_d - 0.1, width=bed_w, depth=0.1
                ),
                # Pillow arc at the head (near rear wall)
                FixtureShape(
                    kind="arc",
                    x=bx + bed_w / 2,
                    y=by + bed_d - 0.25,
                    radius=min(0.35, bed_w / 3),
                    start_deg=0.0,
                    end_deg=180.0,
                ),
            ],
        )
    ]
    st_r = 0.25
    # Fit guard tightened vs the pre-migration renderer: its test allowed
    # the table's CENTRE but not its edge, overflowing the room's right wall
    # by up to 0.25 m on narrow bedrooms (captured cases bedroom@2.4x3.0
    # regenerated after this correction — Task 33 brief's no-overflow rule).
    if (
        bx + bed_w + margin + 2 * st_r <= room.width + 1e-9
        and room.width - (bx + bed_w) > st_r + 0.1
    ):
        fixtures.append(
            Fixture(
                kind="side_table",
                room_id=room.id,
                shapes=[
                    FixtureShape(
                        kind="circle",
                        x=bx + bed_w + margin + st_r,
                        y=by + bed_d - st_r - 0.1,
                        radius=st_r,
                    )
                ],
            )
        )
    return fixtures


# ── Living Room ──────────────────────────────────────────────────────────────


def _living(room: Room) -> list[Fixture]:
    """3-seater sofa against rear wall; coffee table; TV unit on front wall."""
    margin = 0.2
    sofa_w = min(2.4, room.width - 2 * margin)
    sofa_d = 0.9
    if sofa_w < 1.0:
        return []

    sx = (room.width - sofa_w) / 2
    sy = room.depth - margin - sofa_d

    fixtures = [
        Fixture(
            kind="sofa",
            room_id=room.id,
            shapes=[
                # back, then the two armrests
                FixtureShape(kind="rect", x=sx, y=sy, width=sofa_w, depth=sofa_d),
                FixtureShape(kind="rect", x=sx, y=sy, width=0.3, depth=sofa_d),
                FixtureShape(
                    kind="rect", x=sx + sofa_w - 0.3, y=sy, width=0.3, depth=sofa_d
                ),
            ],
        )
    ]

    ct_w = min(1.2, sofa_w * 0.6)
    ct_d = 0.5
    ct_x = (room.width - ct_w) / 2
    ct_y = sy - 0.6 - ct_d
    if ct_y > margin:
        fixtures.append(
            Fixture(
                kind="coffee_table",
                room_id=room.id,
                shapes=[
                    FixtureShape(kind="rect", x=ct_x, y=ct_y, width=ct_w, depth=ct_d)
                ],
            )
        )

    tv_w = min(1.8, room.width - 2 * margin)
    fixtures.append(
        Fixture(
            kind="tv_unit",
            room_id=room.id,
            shapes=[
                FixtureShape(
                    kind="rect",
                    x=(room.width - tv_w) / 2,
                    y=margin,
                    width=tv_w,
                    depth=0.4,
                )
            ],
        )
    )
    return fixtures


# ── Dining Room ──────────────────────────────────────────────────────────────


def _dining(room: Room) -> list[Fixture]:
    """Table centred; chairs (circles) on the long sides + one per short side."""
    margin = 0.4
    tbl_w = min(1.8, room.width - 2 * margin)
    tbl_d = min(0.9, room.depth - 2 * margin)
    if tbl_w < 0.8 or tbl_d < 0.5:
        return []

    tx = (room.width - tbl_w) / 2
    ty = (room.depth - tbl_d) / 2
    fixtures = [
        Fixture(
            kind="dining_table",
            room_id=room.id,
            shapes=[FixtureShape(kind="rect", x=tx, y=ty, width=tbl_w, depth=tbl_d)],
        )
    ]

    # A chair is emitted only when its circle fits INSIDE the room — the
    # pre-migration renderer let chairs spill past narrow/shallow rooms
    # (golden case dining@2.2x1.6 regenerated after this correction —
    # Task 33 brief's no-overflow rule).
    def _chair(cx: float, cyy: float) -> None:
        if not (
            -1e-9 <= cx - chair_r
            and cx + chair_r <= room.width + 1e-9
            and -1e-9 <= cyy - chair_r
            and cyy + chair_r <= room.depth + 1e-9
        ):
            return
        fixtures.append(
            Fixture(
                kind="chair",
                room_id=room.id,
                shapes=[FixtureShape(kind="circle", x=cx, y=cyy, radius=chair_r)],
            )
        )

    chair_r = 0.22
    gap = 0.05
    num_side_chairs = 3 if tbl_w >= 1.5 else 2
    for i in range(num_side_chairs):
        cx = tx + tbl_w / (num_side_chairs + 1) * (i + 1)
        _chair(cx, ty - gap - chair_r)
        _chair(cx, ty + tbl_d + gap + chair_r)
    _chair(tx - gap - chair_r, ty + tbl_d / 2)
    _chair(tx + tbl_w + gap + chair_r, ty + tbl_d / 2)
    return fixtures


# ── Kitchen ──────────────────────────────────────────────────────────────────


def _kitchen(room: Room) -> list[Fixture]:
    """L-shaped counter on rear+left walls; sink (rear-right), stove (rear-left)."""
    margin = 0.05
    cw = 0.6  # counter depth/width
    if room.width < 1.2 or room.depth < 1.2:
        return []

    rw, rd = room.width, room.depth

    rear_y = rd - margin - cw
    rear_x0 = margin
    rear_len = rw - 2 * margin

    fixtures = [
        Fixture(
            kind="counter_rear",
            room_id=room.id,
            shapes=[
                FixtureShape(kind="rect", x=rear_x0, y=rear_y, width=rear_len, depth=cw)
            ],
        )
    ]

    left_len = rd - 2 * margin - cw  # stop before rear counter
    if left_len > 0.5:
        fixtures.append(
            Fixture(
                kind="counter_left",
                room_id=room.id,
                shapes=[
                    FixtureShape(
                        kind="rect", x=margin, y=margin, width=cw, depth=left_len
                    )
                ],
            )
        )

    sink_x = rear_x0 + rear_len - 0.65
    fixtures.append(
        Fixture(
            kind="sink",
            room_id=room.id,
            shapes=[
                FixtureShape(kind="rect", x=sink_x, y=rear_y, width=0.55, depth=cw),
                FixtureShape(
                    kind="circle", x=sink_x + 0.275, y=rear_y + cw / 2, radius=0.18
                ),
            ],
        )
    )

    stove_w = min(0.6, rear_len * 0.4)
    stove_x = rear_x0 + 0.1
    fixtures.append(
        Fixture(
            kind="stove",
            room_id=room.id,
            shapes=[
                FixtureShape(kind="rect", x=stove_x, y=rear_y, width=stove_w, depth=cw)
            ]
            + [
                FixtureShape(kind="circle", x=bx, y=by, radius=0.07)
                for bx, by in [
                    (stove_x + stove_w * 0.3, rear_y + cw * 0.3),
                    (stove_x + stove_w * 0.7, rear_y + cw * 0.3),
                    (stove_x + stove_w * 0.3, rear_y + cw * 0.7),
                    (stove_x + stove_w * 0.7, rear_y + cw * 0.7),
                ]
            ],
        )
    )
    return fixtures


# ── Toilet / Bathroom ────────────────────────────────────────────────────────


def _toilet(room: Room) -> list[Fixture]:
    """WC rear-left; basin front-right; bathtub on the rear wall when big enough."""
    margin = 0.08
    if room.width < 0.8 or room.depth < 0.8:
        return []

    rw, rd = room.width, room.depth

    wc_cx = margin + 0.2
    wc_cy = rd - margin - 0.15  # tank base at the rear wall

    fixtures = [
        Fixture(
            kind="wc",
            room_id=room.id,
            shapes=[
                # tank against the rear wall
                FixtureShape(
                    kind="rect", x=wc_cx - 0.175, y=wc_cy, width=0.35, depth=0.15
                ),
                # bowl: D-shape arc extending toward the room interior (downward)
                FixtureShape(
                    kind="arc",
                    x=wc_cx,
                    y=wc_cy,
                    radius=0.18,
                    start_deg=180.0,
                    end_deg=360.0,
                ),
                FixtureShape(
                    kind="line", x=wc_cx - 0.18, y=wc_cy, x2=wc_cx + 0.18, y2=wc_cy
                ),
            ],
        ),
        Fixture(
            kind="basin",
            room_id=room.id,
            shapes=[
                FixtureShape(
                    kind="circle", x=rw - margin - 0.2, y=margin + 0.2, radius=0.18
                )
            ],
        ),
    ]

    if room.type == "bathroom" and rd >= 1.5 and rw >= 1.2:
        bt_w = min(1.5, rw - 2 * margin)
        bt_d = 0.7
        bt_x = (rw - bt_w) / 2
        bt_y = rd - margin - bt_d
        fixtures.append(
            Fixture(
                kind="bathtub",
                room_id=room.id,
                shapes=[
                    FixtureShape(kind="rect", x=bt_x, y=bt_y, width=bt_w, depth=bt_d),
                    FixtureShape(
                        kind="circle", x=bt_x + bt_w / 2, y=bt_y + bt_d / 2, radius=0.07
                    ),
                ],
            )
        )
    return fixtures


# ── Study / Home Office ──────────────────────────────────────────────────────


def _study(room: Room) -> list[Fixture]:
    """Desk on the rear wall + return on the right; chair; bookshelf left."""
    margin = 0.15
    if room.width < 1.5 or room.depth < 1.5:
        return []

    rw, rd = room.width, room.depth
    desk_d = 0.6  # desk depth

    desk_w = min(1.8, rw - 2 * margin)
    desk_x = (rw - desk_w) / 2
    desk_y = rd - margin - desk_d

    fixtures = [
        Fixture(
            kind="desk",
            room_id=room.id,
            shapes=[
                FixtureShape(
                    kind="rect", x=desk_x, y=desk_y, width=desk_w, depth=desk_d
                )
            ],
        )
    ]

    ret_w = desk_d
    ret_d = min(1.0, rd - 2 * margin - desk_d)
    if ret_d > 0.4:
        fixtures.append(
            Fixture(
                kind="desk_return",
                room_id=room.id,
                shapes=[
                    FixtureShape(
                        kind="rect",
                        x=rw - margin - ret_w,
                        y=desk_y - ret_d,
                        width=ret_w,
                        depth=ret_d,
                    )
                ],
            )
        )

    chair_r = 0.3
    fixtures.append(
        Fixture(
            kind="office_chair",
            room_id=room.id,
            shapes=[
                FixtureShape(
                    kind="circle",
                    x=desk_x + desk_w / 2,
                    y=desk_y - chair_r - 0.1,
                    radius=chair_r,
                )
            ],
        )
    )

    shelf_d = 0.3
    shelf_h = min(1.2, rd - 2 * margin)
    fixtures.append(
        Fixture(
            kind="bookshelf",
            room_id=room.id,
            shapes=[
                FixtureShape(
                    kind="rect", x=margin, y=margin, width=shelf_d, depth=shelf_h
                )
            ],
        )
    )
    return fixtures


# ── Pooja Room ───────────────────────────────────────────────────────────────


def _pooja(room: Room) -> list[Fixture]:
    """Altar platform on the rear wall with a pedestal circle for the idol."""
    margin = 0.1
    if room.width < 0.8 or room.depth < 0.6:
        return []

    rw, rd = room.width, room.depth

    plat_w = min(1.0, rw - 2 * margin)
    plat_d = 0.5
    plat_x = (rw - plat_w) / 2
    plat_y = rd - margin - plat_d
    return [
        Fixture(
            kind="altar",
            room_id=room.id,
            shapes=[
                FixtureShape(
                    kind="rect", x=plat_x, y=plat_y, width=plat_w, depth=plat_d
                ),
                FixtureShape(
                    kind="circle",
                    x=plat_x + plat_w / 2,
                    y=plat_y + plat_d / 2,
                    radius=min(0.15, plat_w / 4),
                ),
            ],
        )
    ]


# ── Balcony ──────────────────────────────────────────────────────────────────


def _balcony(room: Room) -> list[Fixture]:
    """Patio chairs (circles) near the rear wall; small table between them."""
    margin = 0.2
    if room.width < 1.0 or room.depth < 1.0:
        return []

    rw, rd = room.width, room.depth
    chair_r = 0.3

    cy = rd - margin - chair_r
    if rw >= 2.0:
        c1x = rw * 0.25
        c2x = rw * 0.75
        return [
            Fixture(
                kind="patio_chair",
                room_id=room.id,
                shapes=[FixtureShape(kind="circle", x=c1x, y=cy, radius=chair_r)],
            ),
            Fixture(
                kind="patio_chair",
                room_id=room.id,
                shapes=[FixtureShape(kind="circle", x=c2x, y=cy, radius=chair_r)],
            ),
            Fixture(
                kind="patio_table",
                room_id=room.id,
                shapes=[FixtureShape(kind="circle", x=rw / 2, y=cy, radius=0.2)],
            ),
        ]
    return [
        Fixture(
            kind="patio_chair",
            room_id=room.id,
            shapes=[FixtureShape(kind="circle", x=rw / 2, y=cy, radius=chair_r)],
        )
    ]


# ── Utility / Laundry ────────────────────────────────────────────────────────


def _utility(room: Room) -> list[Fixture]:
    """Washing machine (rect + concentric circles) on rear wall; shelf left."""
    margin = 0.1
    if room.width < 0.8 or room.depth < 0.8:
        return []

    rw, rd = room.width, room.depth
    wm_size = 0.6  # washing machine footprint

    wm_x = (rw - wm_size) / 2
    wm_y = rd - margin - wm_size
    cx, cy = wm_x + wm_size / 2, wm_y + wm_size / 2
    fixtures = [
        Fixture(
            kind="washing_machine",
            room_id=room.id,
            shapes=[
                FixtureShape(kind="rect", x=wm_x, y=wm_y, width=wm_size, depth=wm_size),
                FixtureShape(kind="circle", x=cx, y=cy, radius=wm_size * 0.38),
                FixtureShape(kind="circle", x=cx, y=cy, radius=wm_size * 0.18),
            ],
        )
    ]

    shelf_h = min(1.0, rd - 2 * margin)
    if rw > 1.2:
        fixtures.append(
            Fixture(
                kind="shelf",
                room_id=room.id,
                shapes=[
                    FixtureShape(
                        kind="rect", x=margin, y=margin, width=0.3, depth=shelf_h
                    )
                ],
            )
        )
    return fixtures


# ── Servant Quarter ──────────────────────────────────────────────────────────


def _servant_quarter(room: Room) -> list[Fixture]:
    """Single bed (1.0 m) against the rear wall; wardrobe on the left wall."""
    margin = 0.1
    bed_w = min(1.0, room.width - 2 * margin)
    bed_d = min(1.9, room.depth - margin)
    if bed_w < 0.5 or bed_d < 0.5:
        return []

    rw, rd = room.width, room.depth

    bx = (rw - bed_w) / 2
    by = rd - margin - bed_d
    fixtures = [
        Fixture(
            kind="bed",
            room_id=room.id,
            shapes=[
                FixtureShape(kind="rect", x=bx, y=by, width=bed_w, depth=bed_d),
                FixtureShape(
                    kind="rect", x=bx, y=by + bed_d - 0.08, width=bed_w, depth=0.08
                ),
            ],
        )
    ]

    wardrobe_w = 0.55
    wardrobe_h = min(1.2, rd - 2 * margin - bed_d - 0.3)
    if wardrobe_h > 0.4 and rw > 1.3:
        fixtures.append(
            Fixture(
                kind="wardrobe",
                room_id=room.id,
                shapes=[
                    FixtureShape(
                        kind="rect",
                        x=margin,
                        y=margin,
                        width=wardrobe_w,
                        depth=wardrobe_h,
                    )
                ],
            )
        )
    return fixtures


# ── Parking / Garage ─────────────────────────────────────────────────────────


def _parking(room: Room) -> list[Fixture]:
    """Dashed stall outline marking the bay; car silhouette (rect) centred."""
    fixtures = [
        Fixture(
            kind="parking_stall",
            room_id=room.id,
            shapes=[
                FixtureShape(
                    kind="rect",
                    x=0.0,
                    y=0.0,
                    width=room.width,
                    depth=room.depth,
                    dashed=True,
                )
            ],
        )
    ]

    margin = 0.3
    car_w = min(2.0, room.width - 2 * margin)
    car_d = min(4.5, room.depth - 2 * margin)
    if car_w < 0.5 or car_d < 0.5:
        return fixtures

    fixtures.append(
        Fixture(
            kind="car",
            room_id=room.id,
            shapes=[
                FixtureShape(
                    kind="rect",
                    x=(room.width - car_w) / 2,
                    y=(room.depth - car_d) / 2,
                    width=car_w,
                    depth=car_d,
                )
            ],
        )
    )
    return fixtures


# ── Gym ──────────────────────────────────────────────────────────────────────


def _gym(room: Room) -> list[Fixture]:
    """Treadmill rear; dumbbell rack left; dashed exercise mat in the centre."""
    margin = 0.15
    if room.width < 2.0 or room.depth < 2.0:
        return []

    rw, rd = room.width, room.depth

    tm_w = min(1.8, rw - 2 * margin)
    tm_x = (rw - tm_w) / 2
    tm_y = rd - margin - 0.8
    fixtures = [
        Fixture(
            kind="treadmill",
            room_id=room.id,
            shapes=[FixtureShape(kind="rect", x=tm_x, y=tm_y, width=tm_w, depth=0.8)],
        )
    ]

    rack_h = min(1.0, rd - 2 * margin - 0.8 - 0.3)
    if rack_h > 0.4:
        fixtures.append(
            Fixture(
                kind="dumbbell_rack",
                room_id=room.id,
                shapes=[
                    FixtureShape(
                        kind="rect", x=margin, y=margin, width=0.4, depth=rack_h
                    )
                ],
            )
        )
    # NOTE: the mat anchors off rack_h whether or not the rack was drawn —
    # that is the ported pre-migration behaviour, not a typo to "fix".

    mat_x = margin
    mat_y = margin + rack_h + 0.2
    mat_w = rw - 2 * margin
    mat_d = max(0.5, tm_y - mat_y - 0.3)
    if mat_d > 0.5:
        fixtures.append(
            Fixture(
                kind="exercise_mat",
                room_id=room.id,
                shapes=[
                    FixtureShape(
                        kind="rect",
                        x=mat_x,
                        y=mat_y,
                        width=mat_w,
                        depth=mat_d,
                        dashed=True,
                    )
                ],
            )
        )
    return fixtures


# ── Dispatch ─────────────────────────────────────────────────────────────────

_FIXTURE_DISPATCH = {
    "bedroom": _bedroom,
    "master_bedroom": _bedroom,
    "living": _living,
    "dining": _dining,
    "kitchen": _kitchen,
    "toilet": _toilet,
    "bathroom": _toilet,
    "study": _study,
    "home_office": _study,
    "pooja": _pooja,
    "balcony": _balcony,
    "utility": _utility,
    "servant_quarter": _servant_quarter,
    "parking": _parking,
    "garage": _parking,
    "gym": _gym,
    # No furniture: staircase, passage, store_room (empty by design)
}

#: the room types that yield fixtures — pinned by test_furniture.py
FIXTURE_COVERED_TYPES = frozenset(_FIXTURE_DISPATCH)


def derive_fixtures(rooms: list[Room]) -> list[Fixture]:
    """The canonical fixture set for one floor's rooms, in room order; a room
    type outside the dispatch yields nothing (not an error)."""
    out: list[Fixture] = []
    for room in rooms:
        fn = _FIXTURE_DISPATCH.get(room.type)
        if fn is not None:
            out.extend(fn(room))
    return out
