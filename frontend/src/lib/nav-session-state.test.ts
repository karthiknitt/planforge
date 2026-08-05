import { describe, expect, test } from "bun:test";
import { navSessionState, type SessionQuery } from "./nav-session-state";

const SESSION = {} as NonNullable<SessionQuery["data"]>;
const FETCH_ERROR = {} as NonNullable<SessionQuery["error"]>;

function query(overrides: Partial<SessionQuery> = {}): SessionQuery {
  return { isPending: false, data: null, error: null, ...overrides };
}

describe("navSessionState", () => {
  test("pending while the session request is in flight", () =>
    expect(navSessionState(query({ isPending: true }))).toBe("pending"));

  test("pending wins even if stale data is present", () =>
    expect(navSessionState(query({ isPending: true, data: SESSION }))).toBe("pending"));

  test("authenticated when a session is resolved", () =>
    expect(navSessionState(query({ data: SESSION }))).toBe("authenticated"));

  test("anonymous when resolved with no session", () =>
    expect(navSessionState(query({ data: null }))).toBe("anonymous"));

  test("anonymous when the session request failed", () =>
    expect(navSessionState(query({ data: SESSION, error: FETCH_ERROR }))).toBe("anonymous"));

  test("anonymous for a settled, empty query", () =>
    expect(navSessionState(query())).toBe("anonymous"));
});
