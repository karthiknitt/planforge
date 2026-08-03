import { describe, expect, test } from "bun:test";
import { navSessionState } from "./nav-session-state";

describe("navSessionState", () => {
  test("pending while the session request is in flight", () =>
    expect(navSessionState({ isPending: true, data: null, error: null })).toBe("pending"));

  test("pending wins even if stale data is present", () =>
    expect(navSessionState({ isPending: true, data: { user: {} }, error: null })).toBe("pending"));

  test("authenticated when a session is resolved", () =>
    expect(navSessionState({ isPending: false, data: { user: {} }, error: null })).toBe(
      "authenticated"
    ));

  test("anonymous when resolved with no session", () =>
    expect(navSessionState({ isPending: false, data: null, error: null })).toBe("anonymous"));

  test("anonymous when the session request failed", () =>
    expect(
      navSessionState({ isPending: false, data: { user: {} }, error: { message: "boom" } })
    ).toBe("anonymous"));

  test("anonymous when called with no arguments at all", () =>
    expect(navSessionState({})).toBe("anonymous"));
});
