import { describe, expect, it } from "bun:test";
import type { RoomData } from "@/lib/layout-types";
import { buildRoomLabels, plotDimensionLabel, roomLabel } from "./render-annotations";

const ROOMS: RoomData[] = [
  {
    id: "gf-liv",
    name: "Living Room",
    type: "living",
    x: 1.0,
    y: 1.0,
    width: 4.5,
    depth: 3.6,
    area: 16.2,
  },
  {
    id: "gf-bed1",
    name: "Bedroom 1",
    type: "bedroom",
    x: 5.5,
    y: 1.0,
    width: 3.6,
    depth: 3.2,
    area: 11.5,
  },
  {
    id: "gf-kit",
    name: "Kitchen",
    type: "kitchen",
    x: 1.0,
    y: 4.6,
    width: 2.8,
    depth: 3.0,
    area: 8.4,
  },
];

describe("roomLabel", () => {
  it("formats name + dims to one decimal, em-dash separated", () => {
    expect(roomLabel(ROOMS[1])).toBe("BEDROOM 1 — 3.6m × 3.2m");
  });

  it("uppercases the room name", () => {
    expect(roomLabel(ROOMS[0])).toBe("LIVING ROOM — 4.5m × 3.6m");
  });

  it("rounds dimensions to 1 decimal", () => {
    const room: RoomData = { ...ROOMS[0], width: 4.567, depth: 3.049 };
    expect(roomLabel(room)).toBe("LIVING ROOM — 4.6m × 3.0m");
  });
});

describe("buildRoomLabels", () => {
  it("produces exactly one label entry per room", () => {
    const labels = buildRoomLabels(ROOMS);
    expect(labels).toHaveLength(ROOMS.length);
    expect(labels.map((l) => l.id)).toEqual(ROOMS.map((r) => r.id));
  });

  it("centres each label on its room", () => {
    const labels = buildRoomLabels(ROOMS);
    expect(labels[1].cx).toBeCloseTo(5.5 + 3.6 / 2);
    expect(labels[1].cy).toBeCloseTo(1.0 + 3.2 / 2);
  });

  it("carries the formatted label text", () => {
    const labels = buildRoomLabels(ROOMS);
    expect(labels[1].text).toBe("BEDROOM 1 — 3.6m × 3.2m");
  });

  it("clamps font size to a sane readable range", () => {
    const tiny: RoomData = { ...ROOMS[0], width: 0.5, depth: 0.5 };
    const huge: RoomData = { ...ROOMS[0], width: 20, depth: 20 };
    const labels = buildRoomLabels([tiny, huge]);
    expect(labels[0].fontSize).toBeGreaterThanOrEqual(0.12);
    expect(labels[1].fontSize).toBeLessThanOrEqual(0.32);
  });

  it("returns an empty array for no rooms", () => {
    expect(buildRoomLabels([])).toEqual([]);
  });
});

describe("plotDimensionLabel", () => {
  it("formats overall plot footprint to one decimal", () => {
    expect(plotDimensionLabel(9.0, 15.0)).toBe("PLOT 9.0m × 15.0m");
  });
});
