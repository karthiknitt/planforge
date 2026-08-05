import { describe, expect, test } from "bun:test";
import { deriveCardStatus } from "./dashboard-card-status";

describe("deriveCardStatus", () => {
  test("no layouts yet → not_generated, regardless of approvalStatus", () => {
    expect(deriveCardStatus(false, null)).toBe("not_generated");
    // Defensive: approvalStatus shouldn't realistically be set before
    // has_layouts, but a stale/inconsistent read must not crash or lie.
    expect(deriveCardStatus(false, "approved")).toBe("not_generated");
  });

  test("layouts exist, no approval response yet → awaiting", () => {
    expect(deriveCardStatus(true, null)).toBe("awaiting");
  });

  test("layouts exist, approved → approved", () => {
    expect(deriveCardStatus(true, "approved")).toBe("approved");
  });

  test("layouts exist, changes requested → changes_requested", () => {
    expect(deriveCardStatus(true, "changes_requested")).toBe("changes_requested");
  });

  test("an unrecognized approvalStatus string falls back to awaiting, not a crash", () => {
    expect(deriveCardStatus(true, "some_future_status")).toBe("awaiting");
  });
});
