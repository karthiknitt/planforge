"""Structured spatial prompt for AI floor-plan renders.

Pure function over the persisted layout geometry (LayoutOut-shaped dict) —
no API calls, fully unit-testable. The reference/control image (the CAD SVG
or PDF page rendered to PNG) travels alongside this prompt to the provider.
"""

from __future__ import annotations

DEFAULT_STYLE = (
    "photorealistic top-down 3D architectural visualization (dollhouse view), "
    "soft daylight, realistic materials: matte plaster walls, wooden and tiled "
    "flooring appropriate to each room, subtle furniture staging per room type"
)


def _quadrant(x: float, y: float, width_mid: float, length_mid: float) -> str:
    """Coarse position label derived from x/y vs plot midpoints — e.g.
    "front-left". Tolerance bands treat anything near a midpoint as
    "center" on that axis rather than forcing a left/right or front/rear
    call on rooms that straddle the middle."""
    x_tol = width_mid * 0.15
    y_tol = length_mid * 0.15

    if abs(x - width_mid) <= x_tol:
        horizontal = "center"
    elif x < width_mid:
        horizontal = "left"
    else:
        horizontal = "right"

    if abs(y - length_mid) <= y_tol:
        vertical = "center"
    elif y < length_mid:
        vertical = "front"
    else:
        vertical = "rear"

    if vertical == "center" and horizontal == "center":
        return "center"
    if vertical == "center":
        return horizontal
    if horizontal == "center":
        return vertical
    return f"{vertical}-{horizontal}"


def build_render_prompt(
    geometry: dict,
    *,
    plot_length_m: float,
    plot_width_m: float,
    north_direction: str = "N",
    floor: str = "ground_floor",
    style: str = DEFAULT_STYLE,
    reference_kind: str = "cad",
) -> str:
    if floor not in geometry or geometry[floor] is None:
        raise KeyError(f"floor {floor!r} not present in geometry")
    fp = geometry[floor]
    floor_label = floor.replace("_", " ").title()

    room_lines = []
    for r in fp.get("rooms", []):
        room_lines.append(
            f"- {r['name']} ({r['type']}): {r['width']:.1f}m wide x "
            f"{r['depth']:.1f}m deep, positioned {r['x']:.1f}m from the left "
            f"edge and {r['y']:.1f}m from the bottom edge"
        )
    rooms_block = "\n".join(room_lines)

    # Per-room manifest — mirrors the labels burned into the R3F reference
    # image (name + dims + quadrant). Restating them here as text lets the
    # model cross-check the image labels against an independent source
    # instead of only reading pixels.
    width_mid = plot_width_m / 2
    length_mid = plot_length_m / 2
    manifest_lines = [
        f"- {r['name']}: {_quadrant(r['x'], r['y'], width_mid, length_mid)}, "
        f"{r['width']:.1f}m x {r['depth']:.1f}m"
        for r in fp.get("rooms", [])
    ]
    manifest_block = "\n".join(manifest_lines)

    # Data-driven negative constraints — image models routinely hallucinate
    # a parked car, paving or a dining set where the plan has none (and drop
    # rooms the plan does have). Say what must NOT appear, explicitly.
    present = {r["type"] for r in fp.get("rooms", [])}
    negatives: list[str] = []
    if not present & {"parking", "parking_4w", "parking_2w", "garage"}:
        negatives.append(
            "This floor has NO parking, garage, driveway or paved car area — "
            "do not draw a car or parking anywhere."
        )
    if "dining" not in present:
        negatives.append("There is no separate dining room on this floor.")
    else:
        negatives.append(
            "The Dining room MUST be visible and furnished as a dining area."
        )
    if "staircase" in present:
        stair = next(r for r in fp["rooms"] if r["type"] == "staircase")
        negatives.append(
            f"The staircase occupies ONLY its marked position at "
            f"{stair['x']:.1f}m from the left, {stair['y']:.1f}m from the "
            "bottom — keep it there and put nothing else (no car, no "
            "furniture) inside it."
        )
    negatives.append(
        "Render every listed room and NOTHING that is not listed — no extra "
        "rooms, gardens, pools or vehicles."
    )
    negatives_block = "\n".join(f"- {n}" for n in negatives)

    if reference_kind == "r3f":
        reference_instruction = (
            "IMPORTANT: The attached reference image is a 3D geometric model "
            "(solid blocks / wireframe) of this exact floor plan, built from the "
            "same dimensions — treat it as the structural truth. Match the room "
            "positions, proportions and wall layout of the reference exactly — do "
            "not move, resize, add or remove any room. Add realistic materials, "
            "furniture, lighting and finishes on top of the geometry. Walls are "
            "230mm external / 115mm internal."
        )
    else:
        reference_instruction = (
            "IMPORTANT: The attached reference image is the exact CAD floor plan. "
            "Match the room positions, proportions and wall layout of the "
            "reference exactly — do not move, resize, add or remove any room. "
            "Walls are 230mm external / 115mm internal. Keep the same orientation "
            "as the reference image."
        )

    authoritative_instruction = (
        "The room labels shown in the reference image (name + dimensions, "
        "burned directly into the picture) are AUTHORITATIVE and must match "
        "the room manifest above exactly. Rooms must not move, merge, resize, "
        "or be renamed — every room stays in its labelled position with its "
        "labelled dimensions."
    )

    return (
        f"Render the {floor_label} of an Indian residential house "
        f"({plot_length_m:.1f}m x {plot_width_m:.1f}m plot, north facing "
        f"{north_direction}).\n\n"
        f"Rooms (positions and sizes are exact, in metres):\n{rooms_block}\n\n"
        f"Room manifest (name: quadrant, dimensions):\n{manifest_block}\n\n"
        f"Hard constraints:\n{negatives_block}\n\n"
        f"Style: {style}.\n\n"
        f"{reference_instruction}\n\n"
        f"{authoritative_instruction}"
    )
