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


def build_render_prompt(
    geometry: dict,
    *,
    plot_length_m: float,
    plot_width_m: float,
    north_direction: str = "N",
    floor: str = "ground_floor",
    style: str = DEFAULT_STYLE,
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

    return (
        f"Render the {floor_label} of an Indian residential house "
        f"({plot_length_m:.1f}m x {plot_width_m:.1f}m plot, north facing "
        f"{north_direction}).\n\n"
        f"Rooms (positions and sizes are exact, in metres):\n{rooms_block}\n\n"
        f"Style: {style}.\n\n"
        "IMPORTANT: The attached reference image is the exact CAD floor plan. "
        "Match the room positions, proportions and wall layout of the "
        "reference exactly — do not move, resize, add or remove any room. "
        "Walls are 230mm external / 115mm internal. Keep the same orientation "
        "as the reference image."
    )
