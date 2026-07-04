import { describe, expect, test } from "bun:test";
import type { RoomData } from "@/lib/layout-types";
import { detectSharedWalls } from "./floor-plan-svg";

function room(id: string, x: number, y: number, width: number, depth: number): RoomData {
  return { id, name: id, type: "bedroom", x, y, width, depth, area: width * depth };
}

describe("detectSharedWalls", () => {
  test("detects a vertical shared wall between side-by-side rooms", () => {
    const walls = detectSharedWalls([room("a", 0, 0, 3, 4), room("b", 3, 0, 3, 4)]);
    expect(walls).toHaveLength(1);
    expect(walls[0].orientation).toBe("vertical");
    expect(walls[0].wallPos).toBe(3);
    expect(walls[0].segStart).toBe(0);
    expect(walls[0].segEnd).toBe(4);
  });

  test("detects a horizontal shared wall between stacked rooms", () => {
    const walls = detectSharedWalls([room("a", 0, 0, 4, 3), room("b", 0, 3, 4, 3)]);
    expect(walls).toHaveLength(1);
    expect(walls[0].orientation).toBe("horizontal");
    expect(walls[0].wallPos).toBe(3);
  });

  test("ignores rooms separated by a gap", () => {
    expect(detectSharedWalls([room("a", 0, 0, 3, 4), room("b", 3.5, 0, 3, 4)])).toHaveLength(0);
  });

  test("ignores corner-touching rooms (no shared segment)", () => {
    // b starts exactly where a ends on BOTH axes — zero-length overlap
    expect(detectSharedWalls([room("a", 0, 0, 3, 3), room("b", 3, 3, 3, 3)])).toHaveLength(0);
  });

  test("partial overlap yields the overlapping segment only", () => {
    const walls = detectSharedWalls([room("a", 0, 0, 3, 4), room("b", 3, 2, 3, 4)]);
    expect(walls).toHaveLength(1);
    expect(walls[0].segStart).toBe(2);
    expect(walls[0].segEnd).toBe(4);
  });

  test("orders roomA as the left/lower room regardless of input order", () => {
    const walls = detectSharedWalls([room("right", 3, 0, 3, 4), room("left", 0, 0, 3, 4)]);
    expect(walls).toHaveLength(1);
    expect(walls[0].roomA.id).toBe("left");
    expect(walls[0].roomB.id).toBe("right");
  });

  test("tolerates sub-centimetre float noise at the shared edge", () => {
    const walls = detectSharedWalls([room("a", 0, 0, 3.001, 4), room("b", 3.005, 0, 3, 4)]);
    expect(walls).toHaveLength(1);
  });
});
