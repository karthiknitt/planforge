import { describe, expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";

import { FurnitureOverlay } from "@/components/furniture-overlay";
import type { Fixture, RoomData } from "@/lib/layout-types";

const ROOM: RoomData = {
  id: "bed-1",
  name: "Bedroom",
  type: "bedroom",
  x: 1.0,
  y: 2.0,
  width: 3.6,
  depth: 4.4,
  area: 15.84,
};

const FIXTURES: Fixture[] = [
  {
    kind: "bed",
    room_id: "bed-1",
    shapes: [
      {
        kind: "rect",
        x: 1.2,
        y: 2.25,
        width: 1.2,
        depth: 2.0,
        radius: 0,
        start_deg: 0,
        end_deg: 0,
        x2: 0,
        y2: 0,
        dashed: false,
      },
      {
        kind: "arc",
        x: 1.8,
        y: 4.0,
        width: 0,
        depth: 0,
        radius: 0.35,
        start_deg: 0,
        end_deg: 180,
        x2: 0,
        y2: 0,
        dashed: false,
      },
    ],
  },
  {
    kind: "sink",
    room_id: "bed-1",
    shapes: [
      {
        kind: "circle",
        x: 3.0,
        y: 1.0,
        width: 0,
        depth: 0,
        radius: 0.18,
        start_deg: 0,
        end_deg: 0,
        x2: 0,
        y2: 0,
        dashed: false,
      },
    ],
  },
  {
    kind: "wc",
    room_id: "bed-1",
    shapes: [
      {
        kind: "line",
        x: 0.1,
        y: 0.2,
        width: 0,
        depth: 0,
        radius: 0,
        start_deg: 0,
        end_deg: 0,
        x2: 0.5,
        y2: 0.2,
        dashed: false,
      },
    ],
  },
  {
    kind: "parking_stall",
    room_id: "bed-1",
    shapes: [
      {
        kind: "rect",
        x: 0,
        y: 0,
        width: 3.6,
        depth: 4.4,
        radius: 0,
        start_deg: 0,
        end_deg: 0,
        x2: 0,
        y2: 0,
        dashed: true,
      },
    ],
  },
  {
    kind: "bed",
    room_id: "ghost",
    shapes: [
      {
        kind: "rect",
        x: 0,
        y: 0,
        width: 1,
        depth: 1,
        radius: 0,
        start_deg: 0,
        end_deg: 0,
        x2: 0,
        y2: 0,
        dashed: false,
      },
    ],
  },
];

const SCALE = 40;
const OFFSET_X = 10;
const OFFSET_Y = 20;
// plot is 15m high → 600px drawing height
const PLOT_H = 600;

function render(fixtures: Fixture[] = FIXTURES, rooms: RoomData[] = [ROOM]) {
  return renderToStaticMarkup(
    <svg>
      <title>furniture overlay test fixture</title>
      <FurnitureOverlay
        rooms={rooms}
        fixtures={fixtures}
        scale={SCALE}
        offsetX={OFFSET_X}
        offsetY={OFFSET_Y}
        plotHeightPx={PLOT_H}
      />
    </svg>
  );
}

describe("FurnitureOverlay (payload-projected, Task 33)", () => {
  test("renders one SVG element per shape, at room-translated coordinates", () => {
    const html = render();
    // rect: SVG origin top-left = py(y + depth); y-flip = offsetY + H - y*s
    const bedFrameX = OFFSET_X + (ROOM.x + 1.2) * SCALE; // 98
    const bedFrameY = OFFSET_Y + PLOT_H - (ROOM.y + 2.25 + 2.0) * SCALE; // 370
    expect(html).toContain(`x="${bedFrameX}"`);
    expect(html).toContain(`y="${bedFrameY}"`);
    expect(html).toContain(`width="${1.2 * SCALE}"`);
    expect(html).toContain(`height="${2.0 * SCALE}"`);
    // circle
    const cx = OFFSET_X + (ROOM.x + 3.0) * SCALE;
    const cy = OFFSET_Y + PLOT_H - (ROOM.y + 1.0) * SCALE;
    expect(html).toContain(`<circle cx="${cx}" cy="${cy}" r="${0.18 * SCALE}"`);
    // line
    expect(html).toContain("<line");
  });

  test("arcs project as an SVG path whose endpoints match the DXF angles", () => {
    const html = render();
    // centre = room + (1.8, 4.0), r = 0.35; 0° → (+r, 0), 180° → (−r, 0)
    const p1x = OFFSET_X + (ROOM.x + 1.8 + 0.35) * SCALE;
    const p2x = OFFSET_X + (ROOM.x + 1.8 - 0.35) * SCALE;
    const yAt = OFFSET_Y + PLOT_H - (ROOM.y + 4.0) * SCALE;
    expect(html).toContain(
      `d="M ${p1x} ${yAt} A ${0.35 * SCALE} ${0.35 * SCALE} 0 0 0 ${p2x} ${yAt}"`
    );
  });

  test("dashed rects carry a stroke-dasharray", () => {
    const html = render();
    expect(html).toContain('stroke-dasharray="3 2"');
  });

  test("fixtures for unknown rooms are skipped, not rendered at the origin", () => {
    const html = render();
    // the ghost fixture's 1x1 rect at (0,0) must NOT appear
    expect(html).not.toContain(`width="${1 * SCALE}" height="${1 * SCALE}"`);
  });

  test("an empty fixture list renders an empty group", () => {
    const html = render([]);
    expect(html).toContain("furniture-overlay");
    expect(html).not.toContain("<rect");
    expect(html).not.toContain("<circle");
  });

  test("does not filter rooms by on-screen size — the payload already governs that", () => {
    const tiny: RoomData = { ...ROOM, id: "tiny", width: 0.5, depth: 0.5 };
    const tinyFixtures: Fixture[] = [
      {
        kind: "book",
        room_id: "tiny",
        shapes: [
          {
            kind: "rect",
            x: 0,
            y: 0,
            width: 0.5,
            depth: 0.5,
            radius: 0,
            start_deg: 0,
            end_deg: 0,
            x2: 0,
            y2: 0,
            dashed: false,
          },
        ],
      },
    ];
    const html = render(tinyFixtures, [tiny]);
    expect(html).toContain("<rect");
  });
});
