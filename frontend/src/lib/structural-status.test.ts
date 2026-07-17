import { describe, expect, it } from "bun:test";
import {
  changelogCount,
  isPreliminaryStatus,
  needsApproval,
  statusBadgeInfo,
} from "./structural-status";

describe("statusBadgeInfo", () => {
  it("maps draft (and null/undefined) to the muted preliminary badge", () => {
    expect(statusBadgeInfo("draft")).toEqual({ label: "DRAFT · preliminary", tone: "muted" });
    expect(statusBadgeInfo(null)).toEqual({ label: "DRAFT · preliminary", tone: "muted" });
    expect(statusBadgeInfo(undefined)).toEqual({ label: "DRAFT · preliminary", tone: "muted" });
  });

  it("maps approved to an info badge", () => {
    expect(statusBadgeInfo("approved")).toEqual({ label: "APPROVED", tone: "info" });
  });

  it("maps designed to a success badge", () => {
    expect(statusBadgeInfo("designed")).toEqual({
      label: "DESIGNED · IS-code",
      tone: "success",
    });
  });

  it("maps designed_with_warnings to a warning badge", () => {
    expect(statusBadgeInfo("designed_with_warnings")).toEqual({
      label: "DESIGNED · with warnings",
      tone: "warning",
    });
  });

  it("maps stale to a warning badge", () => {
    expect(statusBadgeInfo("stale")).toEqual({ label: "STALE · re-run design", tone: "warning" });
  });

  it("falls back to the draft badge for unknown status strings", () => {
    expect(statusBadgeInfo("something-new")).toEqual({
      label: "DRAFT · preliminary",
      tone: "muted",
    });
  });
});

describe("needsApproval", () => {
  it("is true for draft / null / undefined", () => {
    expect(needsApproval("draft")).toBe(true);
    expect(needsApproval(null)).toBe(true);
    expect(needsApproval(undefined)).toBe(true);
  });

  it("is false once approved or beyond", () => {
    expect(needsApproval("approved")).toBe(false);
    expect(needsApproval("designed")).toBe(false);
    expect(needsApproval("designed_with_warnings")).toBe(false);
  });
});

describe("isPreliminaryStatus", () => {
  it("is true until a live design exists", () => {
    expect(isPreliminaryStatus("draft")).toBe(true);
    expect(isPreliminaryStatus("approved")).toBe(true);
    expect(isPreliminaryStatus(null)).toBe(true);
  });

  it("is false once designed (with or without warnings)", () => {
    expect(isPreliminaryStatus("designed")).toBe(false);
    expect(isPreliminaryStatus("designed_with_warnings")).toBe(false);
  });
});

describe("changelogCount", () => {
  it("counts entries, treating null/undefined as zero", () => {
    expect(changelogCount(["a", "b"])).toBe(2);
    expect(changelogCount([])).toBe(0);
    expect(changelogCount(null)).toBe(0);
    expect(changelogCount(undefined)).toBe(0);
  });
});
