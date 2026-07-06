import { describe, expect, test } from "bun:test";
import { edgeCandidates, snapRect, snapScalar, snapToGrid } from "./canvas-snap";

const room = (id: string, x: number, y: number, w: number, d: number) => ({
  id,
  x,
  y,
  width: w,
  depth: d,
});

describe("snapToGrid", () => {
  test("rounds to nearest 115mm multiple", () => {
    expect(snapToGrid(0.12)).toBeCloseTo(0.115, 6);
    expect(snapToGrid(0.0)).toBe(0);
    expect(snapToGrid(0.23)).toBeCloseTo(0.23, 6);
  });
});

describe("snapScalar", () => {
  test("picks nearest candidate within tolerance", () => {
    expect(snapScalar(3.1, [3.0, 5.0])).toBe(3.0);
  });
  test("returns input when nothing within tolerance", () => {
    expect(snapScalar(4.0, [3.0, 5.0], 0.5)).toBe(4.0);
  });
  test("prefers the closest of several candidates", () => {
    expect(snapScalar(3.09, [3.0, 3.14])).toBe(3.14);
  });
});

describe("edgeCandidates", () => {
  test("collects both edges of other rooms on the axis", () => {
    const rooms = [room("a", 1, 1, 3, 4), room("b", 5, 2, 2, 2)];
    expect(edgeCandidates(rooms, "b", "x").sort()).toEqual([1, 4]);
    expect(edgeCandidates(rooms, "b", "y").sort()).toEqual([1, 5]);
  });
  test("excludes the moving room itself", () => {
    expect(edgeCandidates([room("a", 1, 1, 3, 4)], "a", "x")).toEqual([]);
  });
});

describe("snapRect", () => {
  test("snaps left edge to a neighbor's right edge", () => {
    const moving = room("m", 4.05, 1, 3, 3); // neighbor right edge at 4.0
    const others = [room("n", 1, 1, 3, 3)];
    const snapped = snapRect(moving, others, 12, 15);
    expect(snapped.x).toBeCloseTo(4.0, 6);
    expect(snapped.width).toBe(3); // move never resizes
  });
  test("already-aligned edges are not perturbed by the grid fallback", () => {
    // moving room's y (1) and y+depth (4) already exactly match neighbor
    // edges — snapEdge must not overwrite an exact match with a nearby
    // grid multiple (e.g. 1 -> 1.035).
    const moving = room("m", 4.05, 1, 3, 3);
    const others = [room("n", 1, 1, 3, 3)];
    const snapped = snapRect(moving, others, 12, 15);
    expect(snapped.y).toBe(1);
  });
  test("clamps inside the plot", () => {
    const snapped = snapRect(room("m", -1, -2, 3, 3), [], 12, 15);
    expect(snapped.x).toBeGreaterThanOrEqual(0);
    expect(snapped.y).toBeGreaterThanOrEqual(0);
  });
  test("clamps at the far plot edge", () => {
    const snapped = snapRect(room("m", 11, 14, 3, 3), [], 12, 15);
    expect(snapped.x).toBeCloseTo(9, 6);
    expect(snapped.y).toBeCloseTo(12, 6);
  });
});
