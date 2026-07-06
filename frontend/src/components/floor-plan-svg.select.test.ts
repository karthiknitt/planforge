import { describe, expect, test } from "bun:test";
import { detectSharedWalls } from "./floor-plan-svg";

describe("floor-plan-svg module", () => {
  test("still exports detectSharedWalls after canvas-editor changes", () => {
    expect(typeof detectSharedWalls).toBe("function");
  });
});
