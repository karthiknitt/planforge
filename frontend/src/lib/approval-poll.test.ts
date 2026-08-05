import { describe, expect, test } from "bun:test";
import { isAwaitingApprovalResponse } from "./approval-poll";

describe("isAwaitingApprovalResponse", () => {
  test("shared, no response yet → pollable", () => {
    expect(isAwaitingApprovalResponse("tok123", null)).toBe(true);
  });

  test("never shared → not pollable, even if status is somehow non-null", () => {
    expect(isAwaitingApprovalResponse(null, null)).toBe(false);
    expect(isAwaitingApprovalResponse(undefined, null)).toBe(false);
  });

  test("shared but already resolved (approved) → not pollable", () => {
    expect(isAwaitingApprovalResponse("tok123", "approved")).toBe(false);
  });

  test("shared but already resolved (changes_requested) → not pollable", () => {
    expect(isAwaitingApprovalResponse("tok123", "changes_requested")).toBe(false);
  });

  test("empty-string share token is falsy, not pollable", () => {
    expect(isAwaitingApprovalResponse("", null)).toBe(false);
  });
});
