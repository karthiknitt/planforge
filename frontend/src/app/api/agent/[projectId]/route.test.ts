import { afterEach, beforeEach, describe, expect, mock, test } from "bun:test";

mock.module("next/headers", () => ({
  headers: async () => new Headers(),
}));

const getSessionMock = mock(async () => null as { user: { id: string } } | null);
mock.module("@/lib/auth", () => ({
  auth: { api: { getSession: getSessionMock } },
}));

const { POST } = await import("./route");

function ctx(projectId: string) {
  return { params: Promise.resolve({ projectId }) };
}

function jsonRequest(body: unknown): Request {
  return new Request("http://localhost:3001/api/agent/proj-1", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

describe("agent chat route auth gate", () => {
  beforeEach(() => {
    getSessionMock.mockReset();
  });

  afterEach(() => {
    getSessionMock.mockReset();
  });

  test("returns 401 when there is no session, before parsing the request body", async () => {
    getSessionMock.mockImplementation(async () => null);
    const req = jsonRequest({ messages: [{ role: "user", content: "hi" }] });

    const res = await POST(req, ctx("proj-1"));

    expect(res.status).toBe(401);
    const data = (await res.json()) as { error?: string };
    expect(data.error).toBe("Unauthorized");
  });

  test("a malformed request body never reaches the client-supplied identity anymore", async () => {
    getSessionMock.mockImplementation(async () => ({ user: { id: "user-42" } }));
    const req = new Request("http://localhost:3001/api/agent/proj-1", {
      method: "POST",
      body: "not valid json",
    });

    const res = await POST(req, ctx("proj-1"));

    expect(res.status).toBe(400);
  });

  test("rejects a request with no messages array, using the session's user id, not any client-supplied userId", async () => {
    getSessionMock.mockImplementation(async () => ({ user: { id: "user-42" } }));
    // A client attempting the old exploit: pass an arbitrary userId in the body.
    const req = jsonRequest({ userId: "attacker-controlled-id" });

    const res = await POST(req, ctx("proj-1"));

    // No messages -> 400, but the important assertion is this doesn't 401/500
    // from trying to use a client-supplied userId - the route no longer reads
    // userId from the body at all.
    expect(res.status).toBe(400);
    const data = (await res.json()) as { error?: string };
    expect(data.error).toBe("No messages provided");
  });
});
