import { describe, expect, test } from "bun:test";
import { computePlotPreview } from "./plot-preview";

const input = {
  plotLengthFt: "40", // 12.19 m
  plotWidthFt: "30", // 9.14 m
  setbackFrontFt: "5",
  setbackRearFt: "5",
  setbackLeftFt: "3",
  setbackRightFt: "3",
  roadSide: "S",
};

describe("computePlotPreview", () => {
  test("valid input produces plot, buildable and road boxes", () => {
    const g = computePlotPreview(input, 260, 260);
    expect(g.valid).toBe(true);
    expect(g.plot).not.toBeNull();
    expect(g.buildable).not.toBeNull();
    expect(g.road).not.toBeNull();
  });
  test("buildable is inset within the plot", () => {
    const g = computePlotPreview(input, 260, 260);
    const p = g.plot!;
    const b = g.buildable!;
    expect(b.x).toBeGreaterThan(p.x);
    expect(b.y).toBeGreaterThan(p.y);
    expect(b.x + b.w).toBeLessThan(p.x + p.w);
    expect(b.y + b.h).toBeLessThan(p.y + p.h);
  });
  test("aspect ratio preserved (taller plot → taller box)", () => {
    const g = computePlotPreview(input, 260, 260);
    expect(g.plot!.h).toBeGreaterThan(g.plot!.w); // 40ft deep vs 30ft wide
  });
  test("road sits at the bottom for roadSide S", () => {
    const g = computePlotPreview(input, 260, 260);
    expect(g.road!.y).toBeGreaterThan(g.plot!.y + g.plot!.h - 1);
  });
  test("nonsense input → invalid", () => {
    expect(computePlotPreview({ ...input, plotLengthFt: "" }).valid).toBe(false);
    expect(computePlotPreview({ ...input, plotWidthFt: "-3" }).valid).toBe(false);
  });
  test("setbacks consuming the whole plot → buildable null but still valid", () => {
    const g = computePlotPreview({ ...input, setbackLeftFt: "20", setbackRightFt: "20" });
    expect(g.valid).toBe(true);
    expect(g.buildable).toBeNull();
  });
});
