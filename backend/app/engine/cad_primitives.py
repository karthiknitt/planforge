"""
Professional CAD drawing primitives for PlanForge DXF export.

Produces Indian construction drawing standard output:
- Double-line walls with clean gaps at openings
- Door leaf + arc swing symbols
- Window 3-line + glazing hatch
- Ventilator louvre symbol
- Staircase treads + cut line + UP arrow
- Feet-inches dimension chains
- 8-point compass north arrow
- Bordered title block with area schedule
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------

def metres_to_ftin(m: float) -> str:
    """Convert metres to feet-inches string. e.g. 3.048 → \"10'-0\""""
    total_inches = m / 0.0254
    ft = int(total_inches // 12)
    inch = round(total_inches % 12)
    if inch == 12:
        ft += 1
        inch = 0
    return f"{ft}'-{inch}\""


# ---------------------------------------------------------------------------
# Opening data class
# ---------------------------------------------------------------------------

@dataclass
class Opening:
    """An opening (door / window / ventilator) on a wall segment."""
    wall_key: tuple          # (round(x1,2), round(y1,2), round(x2,2), round(y2,2))
    t_start: float           # normalised position along wall [0..1]
    t_end: float
    kind: str                # "door" | "window" | "ventilator"
    width: float             # metres
    wall_length: float       # used to convert t back to absolute coords
    # centre point in absolute coords (set by collect_openings)
    cx: float = 0.0
    cy: float = 0.0
    is_vertical_wall: bool = False


# ---------------------------------------------------------------------------
# Gap subtraction helper
# ---------------------------------------------------------------------------

def _gap_subtract(total: float, gaps: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Return solid segments of [0..total] after removing all gap intervals."""
    gaps_sorted = sorted(gaps)
    segments: list[tuple[float, float]] = []
    pos = 0.0
    for g_start, g_end in gaps_sorted:
        g_start = max(g_start, 0.0)
        g_end = min(g_end, total)
        if g_start > pos + 1e-6:
            segments.append((pos, g_start))
        pos = max(pos, g_end)
    if pos < total - 1e-6:
        segments.append((pos, total))
    return segments


# ---------------------------------------------------------------------------
# Opening detection
# ---------------------------------------------------------------------------

_HABITABLE = {"living", "bedroom", "master_bedroom", "kitchen", "study", "dining"}
_TOILET_TYPES = {"toilet", "bathroom", "utility"}
_DOOR_WIDTH = 0.9   # metres


def collect_openings(
    rooms: list,
    ewt: float,
    iwt: float,
    bld_x: float,
    bld_y: float,
    bld_w: float,
    bld_d: float,
) -> dict[tuple, list[Opening]]:
    """
    Detect all doors, windows, and ventilators and map them to wall keys.

    Returns dict: wall_key → sorted list of Opening objects.
    Wall key = (round(x1,2), round(y1,2), round(x2,2), round(y2,2)) matching
    the format produced by build_walls_from_rooms in cad_elements.py.
    """
    result: dict[tuple, list[Opening]] = {}

    def _add(op: Opening) -> None:
        result.setdefault(op.wall_key, []).append(op)

    def _vwall_key(x: float) -> tuple:
        return (round(x, 2), round(bld_y, 2), round(x, 2), round(bld_y + bld_d, 2))

    def _hwall_key(y: float) -> tuple:
        return (round(bld_x, 2), round(y, 2), round(bld_x + bld_w, 2), round(y, 2))

    bx2 = bld_x + bld_w
    by2 = bld_y + bld_d

    # ── Doors (room adjacencies) ─────────────────────────────────────────────
    placed_doors: set = set()
    for i, ra in enumerate(rooms):
        for j, rb in enumerate(rooms):
            if j <= i:
                continue

            # Vertical shared wall: ra right ≈ rb left
            if abs(ra.x + ra.width - rb.x) < 0.05:
                y_lo = max(ra.y, rb.y)
                y_hi = min(ra.y + ra.depth, rb.y + rb.depth)
                if y_hi - y_lo > _DOOR_WIDTH + 0.1:
                    wx = ra.x + ra.width
                    my = (y_lo + y_hi) / 2
                    key = (round(wx, 2), round(my, 2), "v")
                    if key not in placed_doors:
                        placed_doors.add(key)
                        wk = _vwall_key(wx)
                        wall_len = bld_d
                        t_c = (my - bld_y) / wall_len
                        half_t = (_DOOR_WIDTH / 2) / wall_len
                        _add(Opening(wk, max(0, t_c - half_t), min(1, t_c + half_t),
                                     "door", _DOOR_WIDTH, wall_len,
                                     cx=wx, cy=my, is_vertical_wall=True))

            # Vertical shared wall: rb right ≈ ra left
            elif abs(rb.x + rb.width - ra.x) < 0.05:
                y_lo = max(ra.y, rb.y)
                y_hi = min(ra.y + ra.depth, rb.y + rb.depth)
                if y_hi - y_lo > _DOOR_WIDTH + 0.1:
                    wx = rb.x + rb.width
                    my = (y_lo + y_hi) / 2
                    key = (round(wx, 2), round(my, 2), "v")
                    if key not in placed_doors:
                        placed_doors.add(key)
                        wk = _vwall_key(wx)
                        wall_len = bld_d
                        t_c = (my - bld_y) / wall_len
                        half_t = (_DOOR_WIDTH / 2) / wall_len
                        _add(Opening(wk, max(0, t_c - half_t), min(1, t_c + half_t),
                                     "door", _DOOR_WIDTH, wall_len,
                                     cx=wx, cy=my, is_vertical_wall=True))

            # Horizontal shared wall: ra top ≈ rb bottom
            if abs(ra.y + ra.depth - rb.y) < 0.05:
                x_lo = max(ra.x, rb.x)
                x_hi = min(ra.x + ra.width, rb.x + rb.width)
                if x_hi - x_lo > _DOOR_WIDTH + 0.1:
                    wy = ra.y + ra.depth
                    mx = (x_lo + x_hi) / 2
                    key = (round(mx, 2), round(wy, 2), "h")
                    if key not in placed_doors:
                        placed_doors.add(key)
                        wk = _hwall_key(wy)
                        wall_len = bld_w
                        t_c = (mx - bld_x) / wall_len
                        half_t = (_DOOR_WIDTH / 2) / wall_len
                        _add(Opening(wk, max(0, t_c - half_t), min(1, t_c + half_t),
                                     "door", _DOOR_WIDTH, wall_len,
                                     cx=mx, cy=wy, is_vertical_wall=False))

            elif abs(rb.y + rb.depth - ra.y) < 0.05:
                x_lo = max(ra.x, rb.x)
                x_hi = min(ra.x + ra.width, rb.x + rb.width)
                if x_hi - x_lo > _DOOR_WIDTH + 0.1:
                    wy = rb.y + rb.depth
                    mx = (x_lo + x_hi) / 2
                    key = (round(mx, 2), round(wy, 2), "h")
                    if key not in placed_doors:
                        placed_doors.add(key)
                        wk = _hwall_key(wy)
                        wall_len = bld_w
                        t_c = (mx - bld_x) / wall_len
                        half_t = (_DOOR_WIDTH / 2) / wall_len
                        _add(Opening(wk, max(0, t_c - half_t), min(1, t_c + half_t),
                                     "door", _DOOR_WIDTH, wall_len,
                                     cx=mx, cy=wy, is_vertical_wall=False))

    # ── Windows (habitable rooms on exterior) ────────────────────────────────
    for room in rooms:
        if room.type not in _HABITABLE:
            continue
        rcx = room.x + room.width / 2
        rcy = room.y + room.depth / 2
        win_w_h = min(1.2, room.width * 0.6)
        win_w_v = min(1.2, room.depth * 0.6)

        if abs(room.y - bld_y) < 0.05:            # front wall
            wk = _hwall_key(bld_y)
            wall_len = bld_w
            t_c = (rcx - bld_x) / wall_len
            half_t = (win_w_h / 2) / wall_len
            _add(Opening(wk, max(0, t_c - half_t), min(1, t_c + half_t),
                         "window", win_w_h, wall_len, cx=rcx, cy=bld_y))
        elif abs(room.y + room.depth - by2) < 0.05:  # rear wall
            wk = _hwall_key(by2)
            wall_len = bld_w
            t_c = (rcx - bld_x) / wall_len
            half_t = (win_w_h / 2) / wall_len
            _add(Opening(wk, max(0, t_c - half_t), min(1, t_c + half_t),
                         "window", win_w_h, wall_len, cx=rcx, cy=by2))

        if abs(room.x - bld_x) < 0.05:            # left wall
            wk = _vwall_key(bld_x)
            wall_len = bld_d
            t_c = (rcy - bld_y) / wall_len
            half_t = (win_w_v / 2) / wall_len
            _add(Opening(wk, max(0, t_c - half_t), min(1, t_c + half_t),
                         "window", win_w_v, wall_len, cx=bld_x, cy=rcy, is_vertical_wall=True))
        elif abs(room.x + room.width - bx2) < 0.05:  # right wall
            wk = _vwall_key(bx2)
            wall_len = bld_d
            t_c = (rcy - bld_y) / wall_len
            half_t = (win_w_v / 2) / wall_len
            _add(Opening(wk, max(0, t_c - half_t), min(1, t_c + half_t),
                         "window", win_w_v, wall_len, cx=bx2, cy=rcy, is_vertical_wall=True))

    # ── Ventilators (toilet/bathroom on exterior) ────────────────────────────
    vent_w = 0.6
    for room in rooms:
        if room.type not in _TOILET_TYPES:
            continue
        rcx = room.x + room.width / 2
        rcy = room.y + room.depth / 2

        if abs(room.y - bld_y) < 0.05:
            wk = _hwall_key(bld_y)
            wall_len = bld_w
            t_c = (rcx - bld_x) / wall_len
            half_t = (vent_w / 2) / wall_len
            _add(Opening(wk, max(0, t_c - half_t), min(1, t_c + half_t),
                         "ventilator", vent_w, wall_len, cx=rcx, cy=bld_y))
        elif abs(room.y + room.depth - by2) < 0.05:
            wk = _hwall_key(by2)
            wall_len = bld_w
            t_c = (rcx - bld_x) / wall_len
            half_t = (vent_w / 2) / wall_len
            _add(Opening(wk, max(0, t_c - half_t), min(1, t_c + half_t),
                         "ventilator", vent_w, wall_len, cx=rcx, cy=by2))
        if abs(room.x - bld_x) < 0.05:
            wk = _vwall_key(bld_x)
            wall_len = bld_d
            t_c = (rcy - bld_y) / wall_len
            half_t = (vent_w / 2) / wall_len
            _add(Opening(wk, max(0, t_c - half_t), min(1, t_c + half_t),
                         "ventilator", vent_w, wall_len, cx=bld_x, cy=rcy, is_vertical_wall=True))
        elif abs(room.x + room.width - bx2) < 0.05:
            wk = _vwall_key(bx2)
            wall_len = bld_d
            t_c = (rcy - bld_y) / wall_len
            half_t = (vent_w / 2) / wall_len
            _add(Opening(wk, max(0, t_c - half_t), min(1, t_c + half_t),
                         "ventilator", vent_w, wall_len, cx=bx2, cy=rcy, is_vertical_wall=True))

    # Sort each wall's openings by t_start
    for ops in result.values():
        ops.sort(key=lambda o: o.t_start)

    return result


# ---------------------------------------------------------------------------
# Wall drawing with breaks
# ---------------------------------------------------------------------------

def draw_wall_with_breaks(msp, wall, openings: list[Opening], layer: str, z: float) -> None:
    """Draw double-line wall leaving gaps at opening positions."""
    from ezdxf import colors as _c  # noqa: F401 — imported for side-effects in ezdxf internals

    dx = wall.x2 - wall.x1
    dy = wall.y2 - wall.y1
    length = math.hypot(dx, dy)
    if length < 0.001:
        return

    px = -dy / length   # perpendicular unit vector
    py = dx / length
    h = wall.thickness / 2

    gaps = [(op.t_start * length, op.t_end * length) for op in openings]
    segments = _gap_subtract(length, gaps)

    for s_start, s_end in segments:
        t0 = s_start / length
        t1 = s_end / length

        # Inner face
        p1 = (wall.x1 + t0 * dx + h * px, wall.y1 + t0 * dy + h * py, z)
        p2 = (wall.x1 + t1 * dx + h * px, wall.y1 + t1 * dy + h * py, z)
        msp.add_line(p1, p2, dxfattribs={"layer": layer, "lineweight": 50})

        # Outer face
        p3 = (wall.x1 + t0 * dx - h * px, wall.y1 + t0 * dy - h * py, z)
        p4 = (wall.x1 + t1 * dx - h * px, wall.y1 + t1 * dy - h * py, z)
        msp.add_line(p3, p4, dxfattribs={"layer": layer, "lineweight": 50})

        # Solid fill for cut wall sections (IS:962 / AIA floor-plan convention).
        # Note: 'elevation' must NOT be in dxfattribs for HATCH entities — it
        # causes TypeError in ezdxf. Z-stacking is not needed for 2D plan hatches.
        hatch_corners = [
            (p1[0], p1[1]),
            (p2[0], p2[1]),
            (p4[0], p4[1]),
            (p3[0], p3[1]),
        ]
        try:
            hatch = msp.add_hatch(
                color=0,  # ByBlock → renders as black
                dxfattribs={"layer": layer, "lineweight": 9},
            )
            hatch.set_solid_fill()
            hatch.paths.add_polyline_path(hatch_corners, is_closed=True)
        except Exception as exc:
            logger.warning("Wall hatch failed on layer %s: %s", layer, exc)


# ---------------------------------------------------------------------------
# Door symbol
# ---------------------------------------------------------------------------

def draw_door(
    msp,
    cx: float,
    cy: float,
    width: float,
    is_vertical_wall: bool,
    swing_left: bool,
    layer: str,
    z: float,
) -> None:
    """Draw door leaf (line) + quarter-circle arc swing."""
    if is_vertical_wall:
        # Door leaf runs perpendicular (horizontal) into room
        hinge_y = cy - width / 2 if swing_left else cy + width / 2
        leaf_end_x = cx + width if swing_left else cx - width
        msp.add_line((cx, hinge_y, z), (leaf_end_x, hinge_y, z), dxfattribs={"layer": layer, "lineweight": 25})
        if swing_left:
            msp.add_arc(center=(cx, hinge_y), radius=width,
                        start_angle=0, end_angle=90,
                        dxfattribs={"layer": layer, "elevation": z, "lineweight": 25})
        else:
            msp.add_arc(center=(cx, hinge_y), radius=width,
                        start_angle=90, end_angle=180,
                        dxfattribs={"layer": layer, "elevation": z, "lineweight": 25})
    else:
        # Door leaf runs perpendicular (vertical) into room
        hinge_x = cx - width / 2 if swing_left else cx + width / 2
        leaf_end_y = cy + width if swing_left else cy - width
        msp.add_line((hinge_x, cy, z), (hinge_x, leaf_end_y, z), dxfattribs={"layer": layer, "lineweight": 25})
        if swing_left:
            msp.add_arc(center=(hinge_x, cy), radius=width,
                        start_angle=0, end_angle=90,
                        dxfattribs={"layer": layer, "elevation": z, "lineweight": 25})
        else:
            msp.add_arc(center=(hinge_x, cy), radius=width,
                        start_angle=270, end_angle=360,
                        dxfattribs={"layer": layer, "elevation": z, "lineweight": 25})


# ---------------------------------------------------------------------------
# Window symbol
# ---------------------------------------------------------------------------

def draw_window(
    msp,
    cx: float,
    cy: float,
    width: float,
    is_horizontal: bool,
    wall_thickness: float,
    layer: str,
    z: float,
) -> None:
    """3-line window symbol with ANSI31 glazing hatch between outer lines."""
    hw = width / 2
    offsets = [-wall_thickness / 2, 0.0, wall_thickness / 2]

    outer_pts: list[tuple] = []

    for i, off in enumerate(offsets):
        if is_horizontal:
            p1 = (cx - hw, cy + off, z)
            p2 = (cx + hw, cy + off, z)
        else:
            p1 = (cx + off, cy - hw, z)
            p2 = (cx + off, cy + hw, z)
        msp.add_line(p1, p2, dxfattribs={"layer": layer, "lineweight": 25})
        if i == 0:
            outer_pts = [p1, p2]
        elif i == 2:
            outer_pts += [p2, p1]

    # Glazing hatch between the two outer lines
    try:
        hatch_corners_2d = [(p[0], p[1]) for p in outer_pts]
        hatch = msp.add_hatch(dxfattribs={"layer": layer, "lineweight": 9})
        hatch.set_pattern_fill("ANSI31", scale=0.02)
        hatch.paths.add_polyline_path(hatch_corners_2d, is_closed=True)
    except Exception as exc:
        logger.warning("Window hatch failed on layer %s: %s", layer, exc)


# ---------------------------------------------------------------------------
# Ventilator symbol
# ---------------------------------------------------------------------------

def draw_ventilator(
    msp,
    cx: float,
    cy: float,
    is_horizontal: bool,
    layer: str,
    z: float,
) -> None:
    """4-line louvre symbol for ventilators (0.6 m wide)."""
    width = 0.6
    hw = width / 2
    offsets = [-0.105, -0.035, 0.035, 0.105]

    for off in offsets:
        if is_horizontal:
            msp.add_line((cx - hw, cy + off, z), (cx + hw, cy + off, z),
                         dxfattribs={"layer": layer, "lineweight": 25})
        else:
            msp.add_line((cx + off, cy - hw, z), (cx + off, cy + hw, z),
                         dxfattribs={"layer": layer, "lineweight": 25})


# ---------------------------------------------------------------------------
# Staircase
# ---------------------------------------------------------------------------

def draw_staircase(msp, room, layer: str, z: float) -> None:
    """Draw staircase treads, diagonal cut line, and UP arrow."""
    rx, ry, rw, rd = room.x, room.y, room.width, room.depth

    if rd >= rw:
        # Stairs run N-S; treads are horizontal lines
        tread_count = max(2, int(rd / 0.25))
        for i in range(1, tread_count):
            y = ry + i * (rd / tread_count)
            msp.add_line((rx, y, z), (rx + rw, y, z), dxfattribs={"layer": layer, "lineweight": 25})
    else:
        # Stairs run E-W; treads are vertical lines
        tread_count = max(2, int(rw / 0.25))
        for i in range(1, tread_count):
            x = rx + i * (rw / tread_count)
            msp.add_line((x, ry, z), (x, ry + rd, z), dxfattribs={"layer": layer, "lineweight": 25})

    # Diagonal cut line (zig-zag at ~60% height)
    mid_y = ry + rd * 0.6
    msp.add_lwpolyline(
        [(rx, mid_y), (rx + rw * 0.4, mid_y + 0.15),
         (rx + rw * 0.6, mid_y - 0.15), (rx + rw, mid_y)],
        dxfattribs={"layer": layer, "elevation": z, "lineweight": 25},
    )

    # Direction arrow
    arrow_x = rx + rw / 2
    arrow_y_start = ry + 0.15
    arrow_y_end = ry + rd * 0.55
    msp.add_line((arrow_x, arrow_y_start, z), (arrow_x, arrow_y_end, z),
                 dxfattribs={"layer": layer, "lineweight": 25})
    msp.add_mtext(
        "UP",
        dxfattribs={
            "layer": layer,
            "char_height": 0.18,
            "insert": (arrow_x, arrow_y_end + 0.1, z),
            "attachment_point": 5,
        },
    )


# ---------------------------------------------------------------------------
# Dimension chain (feet-inches)
# ---------------------------------------------------------------------------

def draw_dimension_chain(
    msp,
    positions: list[float],
    fixed_coord: float,
    offset: float,
    is_horizontal: bool,
    layer: str,
    z: float,
) -> None:
    """
    Draw a chain of linear dimensions between consecutive positions.
    Text is in feet-inches format (metres_to_ftin).
    """
    if len(positions) < 2:
        return

    # ARCH_MM dimstyle is created once in export.py before modelspace is obtained.
    # draw_dimension_chain() relies on it already existing in the document.
    for i in range(len(positions) - 1):
        p_start = positions[i]
        p_end = positions[i + 1]
        span = p_end - p_start
        if span < 0.05:
            continue
        dim_text = metres_to_ftin(span)

        if is_horizontal:
            base = (p_start, fixed_coord + offset)
            p1 = (p_start, fixed_coord)
            p2 = (p_end, fixed_coord)
            angle = 0
        else:
            base = (fixed_coord + offset, p_start)
            p1 = (fixed_coord, p_start)
            p2 = (fixed_coord, p_end)
            angle = 90

        try:
            dim = msp.add_linear_dim(
                base=base,
                p1=p1,
                p2=p2,
                angle=angle,
                dimstyle="ARCH_MM",
                dxfattribs={"layer": layer, "lineweight": 18},
            )
            dim.set_text(dim_text)
            dim.render()
        except Exception as exc:
            logger.warning("Dimension render failed: %s", exc)

    # Overall outer dimension (0.8 m further out)
    total = positions[-1] - positions[0]
    outer_offset = offset + (0.8 if offset < 0 else 0.8)
    if is_horizontal:
        base_outer = (positions[0], fixed_coord + outer_offset)
        p1_outer = (positions[0], fixed_coord)
        p2_outer = (positions[-1], fixed_coord)
        angle_outer = 0
    else:
        base_outer = (fixed_coord + outer_offset, positions[0])
        p1_outer = (fixed_coord, positions[0])
        p2_outer = (fixed_coord, positions[-1])
        angle_outer = 90

    try:
        dim = msp.add_linear_dim(
            base=base_outer,
            p1=p1_outer,
            p2=p2_outer,
            angle=angle_outer,
            dimstyle="ARCH_MM",
            dxfattribs={"layer": layer, "lineweight": 18},
        )
        dim.set_text(metres_to_ftin(total))
        dim.render()
    except Exception as exc:
        logger.warning("Outer dimension render failed: %s", exc)


# ---------------------------------------------------------------------------
# North arrow (8-point compass rose)
# ---------------------------------------------------------------------------

def draw_north_arrow(
    msp,
    cx: float,
    cy: float,
    north_dir: str,
    size: float,
    layer: str,
) -> None:
    """Draw an 8-point compass rose with filled north spike."""
    # Cardinal directions (N/S/E/W): full length spikes
    cardinal_angles = {"N": 90, "E": 0, "S": 270, "W": 180}
    # Diagonal directions: 60% length
    diag_angles = [45, 135, 225, 315]

    for direction, base_angle in cardinal_angles.items():
        angle_rad = math.radians(base_angle)
        tip_x = cx + size * math.cos(angle_rad)
        tip_y = cy + size * math.sin(angle_rad)

        # Wing points (15° either side at 30% of size from centre)
        left_rad = math.radians(base_angle + 15)
        right_rad = math.radians(base_angle - 15)
        lx = cx + size * 0.3 * math.cos(left_rad)
        ly = cy + size * 0.3 * math.sin(left_rad)
        rx = cx + size * 0.3 * math.cos(right_rad)
        ry = cy + size * 0.3 * math.sin(right_rad)

        spike_pts = [(lx, ly), (tip_x, tip_y), (rx, ry), (cx, cy)]
        msp.add_lwpolyline(spike_pts, close=True, dxfattribs={"layer": layer, "lineweight": 25})

        # Fill north spike
        if direction == north_dir:
            try:
                hatch = msp.add_hatch(dxfattribs={"layer": layer})
                hatch.set_solid_fill(color=7)  # white = black on print
                hatch.paths.add_polyline_path(
                    [(lx, ly), (tip_x, tip_y), (rx, ry), (cx, cy)],
                    is_closed=True,
                )
            except Exception as exc:
                logger.warning("North arrow hatch failed: %s", exc)

        # Compass label
        label_x = cx + (size + 0.2) * math.cos(angle_rad)
        label_y = cy + (size + 0.2) * math.sin(angle_rad)
        msp.add_mtext(
            direction,
            dxfattribs={
                "layer": layer,
                "char_height": 0.2,
                "insert": (label_x, label_y),
                "attachment_point": 5,
                "lineweight": 25,
            },
        )

    # Short diagonal spikes
    for angle_deg in diag_angles:
        angle_rad = math.radians(angle_deg)
        tip_x = cx + size * 0.6 * math.cos(angle_rad)
        tip_y = cy + size * 0.6 * math.sin(angle_rad)
        msp.add_line((cx, cy), (tip_x, tip_y), dxfattribs={"layer": layer, "lineweight": 25})


# ---------------------------------------------------------------------------
# Scale bar (graphical 1:100 bar)
# ---------------------------------------------------------------------------

def draw_scale_bar(msp, x: float, y: float, layer: str, z: float = 0) -> None:
    """Draw a 3m graphical scale bar subdivided at 0, 1m, 2m, 3m."""
    tick_h = 0.1  # tick half-height above and below bar
    labels = ["0", "1m", "2m", "3m"]

    # Horizontal bar (0 to 3m)
    msp.add_line((x, y, z), (x + 3.0, y, z), dxfattribs={"layer": layer, "lineweight": 25})

    # Tick marks and labels at each metre
    for i, label in enumerate(labels):
        tx = x + float(i)
        msp.add_line((tx, y, z), (tx, y + tick_h, z), dxfattribs={"layer": layer, "lineweight": 25})
        msp.add_line((tx, y, z), (tx, y - tick_h, z), dxfattribs={"layer": layer, "lineweight": 25})
        msp.add_mtext(
            label,
            dxfattribs={
                "layer": layer,
                "char_height": 0.18,
                "insert": (tx, y + tick_h + 0.05, z),
                "attachment_point": 8,  # BOTTOM_CENTER
                "lineweight": 18,
            },
        )

    # "SCALE 1:100" title above bar
    msp.add_mtext(
        "SCALE 1:100",
        dxfattribs={
            "layer": layer,
            "char_height": 0.2,
            "insert": (x + 1.5, y + tick_h + 0.35, z),
            "attachment_point": 5,  # MIDDLE_CENTER
            "lineweight": 18,
        },
    )


# ---------------------------------------------------------------------------
# Title block
# ---------------------------------------------------------------------------

def draw_title_block(
    msp,
    project_name: str,
    layout_id: str,
    gf_area_sqft: float,
    ff_area_sqft: float,
    plot_w: float,
    plot_l: float,
    insert_x: float,
    insert_y: float,
) -> None:
    """Draw bordered title block with area schedule and opening legend."""
    blk_w = 12.0
    blk_h = 4.0
    x0, y0 = insert_x, insert_y

    # Outer border
    border = [
        (x0, y0), (x0 + blk_w, y0),
        (x0 + blk_w, y0 + blk_h), (x0, y0 + blk_h),
    ]
    msp.add_lwpolyline(border, close=True, dxfattribs={"layer": "A-TITLE", "lineweight": 50})

    # Title row divider at y0+blk_h-0.9
    title_row_y = y0 + blk_h - 0.9
    msp.add_line((x0, title_row_y), (x0 + blk_w, title_row_y),
                 dxfattribs={"layer": "A-TITLE"})

    # Vertical divider at x0 + blk_w/2
    mid_x = x0 + blk_w / 2
    msp.add_line((mid_x, y0), (mid_x, title_row_y), dxfattribs={"layer": "A-TITLE"})

    # Title text (centred, underlined via MTEXT formatting)
    msp.add_mtext(
        f"{{\\L{project_name} — LAYOUT {layout_id}}}",
        dxfattribs={
            "layer": "A-TITLE",
            "char_height": 0.35,
            "insert": (x0 + blk_w / 2, y0 + blk_h - 0.45),
            "attachment_point": 5,
            "width": blk_w - 0.2,
        },
    )

    # Left column: area info
    left_text = (
        f"GROUND FLOOR BUILDUP AREA\\P"
        f"= {gf_area_sqft:.0f} SQFT\\P\\P"
        f"FIRST FLOOR BUILDUP AREA\\P"
        f"= {ff_area_sqft:.0f} SQFT\\P\\P"
        f"PlanForge  |  Generated by AI"
    )
    msp.add_mtext(
        left_text,
        dxfattribs={
            "layer": "A-TITLE",
            "char_height": 0.22,
            "insert": (x0 + 0.2, title_row_y - 0.2),
            "attachment_point": 1,  # TOP_LEFT
            "width": mid_x - x0 - 0.3,
        },
    )

    # Right column: opening schedule
    schedule_text = (
        "MEASUREMENTS:\\P"
        "MD - (3'6\"x7'0\") Main Door\\P"
        "D  - (3'0\"x7'0\") Door\\P"
        "D1 - (2'6\"x7'0\") Bedroom Door\\P"
        "W  - (6'0\"x4'0\") Window\\P"
        "KW - (4'0\"x3'0\") Kitchen Window\\P"
        "V  - (2'0\"x2'0\") Ventilator"
    )
    msp.add_mtext(
        schedule_text,
        dxfattribs={
            "layer": "A-TITLE",
            "char_height": 0.18,
            "insert": (mid_x + 0.2, title_row_y - 0.2),
            "attachment_point": 1,  # TOP_LEFT
            "width": blk_w / 2 - 0.3,
        },
    )
