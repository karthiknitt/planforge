"""
Professional CAD drawing primitives for PlanForge DXF export.

Produces Indian construction drawing standard output:
- Feet-inches unit conversion
- 8-point compass north arrow
- Graphical scale bar
- Bordered title block with area schedule

Wall, opening, staircase, and dimension-chain geometry come from the
canonical FloorDrawing (`app.engine.plan_geometry.build_floor_drawing`) —
this module no longer derives them privately.
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)


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
# North arrow (8-point compass rose)
# ---------------------------------------------------------------------------


def draw_north_arrow(
    msp,
    cx: float,
    cy: float,
    north_angle_deg: float,
    size: float,
    layer: str,
) -> None:
    """Draw an 8-point compass rose whose filled N spike points at true north.

    `north_angle_deg` is the clockwise angle from the plot's +y axis to true
    north (see `app.engine.vastu.resolve_north_angle`). The rose's spikes sit
    at fixed sheet angles in CAD convention (0°=+x, counterclockwise):
    N=90°, E=0°, S=270°, W=180°. Subtracting `north_angle_deg` from every
    spike/label angle rotates the whole rose so its N spike points at true
    north on the sheet — e.g. a south-facing road (0°) leaves N at 90° (up),
    an east-facing road (90°) swings N to 0° (right).
    """
    # Cardinal directions (N/S/E/W): full length spikes
    cardinal_angles = {"N": 90, "E": 0, "S": 270, "W": 180}
    # Diagonal directions: 60% length
    diag_angles = [45, 135, 225, 315]

    for direction, base_angle in cardinal_angles.items():
        angle_rad = math.radians(base_angle - north_angle_deg)
        tip_x = cx + size * math.cos(angle_rad)
        tip_y = cy + size * math.sin(angle_rad)

        # Wing points (15° either side at 30% of size from centre)
        left_rad = math.radians(base_angle - north_angle_deg + 15)
        right_rad = math.radians(base_angle - north_angle_deg - 15)
        lx = cx + size * 0.3 * math.cos(left_rad)
        ly = cy + size * 0.3 * math.sin(left_rad)
        rx = cx + size * 0.3 * math.cos(right_rad)
        ry = cy + size * 0.3 * math.sin(right_rad)

        spike_pts = [(lx, ly), (tip_x, tip_y), (rx, ry), (cx, cy)]
        msp.add_lwpolyline(
            spike_pts, close=True, dxfattribs={"layer": layer, "lineweight": 25}
        )

        # Fill the N spike — the rose is rotated to make N point at true north
        if direction == "N":
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
        angle_rad = math.radians(angle_deg - north_angle_deg)
        tip_x = cx + size * 0.6 * math.cos(angle_rad)
        tip_y = cy + size * 0.6 * math.sin(angle_rad)
        msp.add_line(
            (cx, cy), (tip_x, tip_y), dxfattribs={"layer": layer, "lineweight": 25}
        )


# ---------------------------------------------------------------------------
# Scale bar (graphical 1:100 bar)
# ---------------------------------------------------------------------------


def draw_scale_bar(msp, x: float, y: float, layer: str, z: float = 0) -> None:
    """Draw a 3m graphical scale bar subdivided at 0, 1m, 2m, 3m."""
    tick_h = 0.1  # tick half-height above and below bar
    labels = ["0", "1m", "2m", "3m"]

    # Horizontal bar (0 to 3m)
    msp.add_line(
        (x, y, z), (x + 3.0, y, z), dxfattribs={"layer": layer, "lineweight": 25}
    )

    # Tick marks and labels at each metre
    for i, label in enumerate(labels):
        tx = x + float(i)
        msp.add_line(
            (tx, y, z),
            (tx, y + tick_h, z),
            dxfattribs={"layer": layer, "lineweight": 25},
        )
        msp.add_line(
            (tx, y, z),
            (tx, y - tick_h, z),
            dxfattribs={"layer": layer, "lineweight": 25},
        )
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


def _draw_text_lines(
    msp, lines: list[str], x: float, y: float, char_height: float, layer: str
) -> None:
    """Draw plain TEXT entities top-anchored at (x, y), one per line, stepping
    downward. Blank strings advance the row without drawing (paragraph gap)."""
    from ezdxf.enums import TextEntityAlignment

    line_h = char_height * 1.4
    for i, line in enumerate(lines):
        if not line:
            continue
        entity = msp.add_text(line, dxfattribs={"layer": layer, "height": char_height})
        entity.set_placement((x, y - i * line_h), align=TextEntityAlignment.TOP_LEFT)


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
    """Draw bordered title block with area schedule and opening legend.

    Uses plain TEXT entities throughout (no MTEXT \\P/{\\L...} formatting
    codes) — some DXF viewers/plotters garble those escape sequences.
    """
    from ezdxf.enums import TextEntityAlignment

    blk_w = 12.0
    blk_h = 4.0
    x0, y0 = insert_x, insert_y

    # Outer border
    border = [
        (x0, y0),
        (x0 + blk_w, y0),
        (x0 + blk_w, y0 + blk_h),
        (x0, y0 + blk_h),
    ]
    msp.add_lwpolyline(
        border, close=True, dxfattribs={"layer": "A-TITLE", "lineweight": 50}
    )

    # Title row divider at y0+blk_h-0.9
    title_row_y = y0 + blk_h - 0.9
    msp.add_line(
        (x0, title_row_y), (x0 + blk_w, title_row_y), dxfattribs={"layer": "A-TITLE"}
    )

    # Vertical divider at x0 + blk_w/2
    mid_x = x0 + blk_w / 2
    msp.add_line((mid_x, y0), (mid_x, title_row_y), dxfattribs={"layer": "A-TITLE"})

    # Title text (centred, plain TEXT)
    title = msp.add_text(
        f"{project_name} — LAYOUT {layout_id}",
        dxfattribs={"layer": "A-TITLE", "height": 0.35},
    )
    title.set_placement(
        (x0 + blk_w / 2, y0 + blk_h - 0.45), align=TextEntityAlignment.MIDDLE_CENTER
    )

    # Left column: area info
    left_lines = [
        "GROUND FLOOR BUILDUP AREA",
        f"= {gf_area_sqft:.0f} SQFT",
        "",
        "FIRST FLOOR BUILDUP AREA",
        f"= {ff_area_sqft:.0f} SQFT",
        "",
        "PlanForge  |  Generated by AI",
    ]
    _draw_text_lines(msp, left_lines, x0 + 0.2, title_row_y - 0.3, 0.22, "A-TITLE")

    # Right column: opening schedule
    schedule_lines = [
        "MEASUREMENTS:",
        "MD - (3'6\"x7'0\") Main Door",
        "D  - (3'0\"x7'0\") Door",
        "D1 - (2'6\"x7'0\") Bedroom Door",
        "W  - (6'0\"x4'0\") Window",
        "KW - (4'0\"x3'0\") Kitchen Window",
        "V  - (2'0\"x2'0\") Ventilator",
    ]
    _draw_text_lines(
        msp, schedule_lines, mid_x + 0.2, title_row_y - 0.3, 0.18, "A-TITLE"
    )
