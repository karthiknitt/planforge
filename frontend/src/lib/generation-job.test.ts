import { describe, expect, test } from "bun:test";
import { jobPhase, stageLabel } from "./generation-job";

describe("jobPhase", () => {
  test("null job is idle", () => expect(jobPhase(null)).toBe("idle"));
  test("queued", () =>
    expect(jobPhase({ id: "1", status: "queued", stage: "queued", error: null })).toBe("queued"));
  test("running", () =>
    expect(jobPhase({ id: "1", status: "running", stage: "solving", error: null })).toBe(
      "running"
    ));
  test("done", () =>
    expect(jobPhase({ id: "1", status: "done", stage: "stored", error: null })).toBe("done"));
  test("failed", () =>
    expect(jobPhase({ id: "1", status: "failed", stage: "failed", error: "x" })).toBe("failed"));
  test("unknown status treated as running (keep polling)", () =>
    expect(jobPhase({ id: "1", status: "weird", stage: "?", error: null })).toBe("running"));
});

describe("stageLabel", () => {
  test("solving", () => expect(stageLabel("solving")).toBe("Solving layouts…"));
  test("stored", () => expect(stageLabel("stored")).toBe("Finalizing…"));
  test("unknown falls back to Working", () => expect(stageLabel("x")).toBe("Working…"));
});
