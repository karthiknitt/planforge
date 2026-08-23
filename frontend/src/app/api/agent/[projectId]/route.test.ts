import { afterEach, beforeEach, describe, expect, test } from "bun:test";

import { getSessionMock } from "@/test/setup";

const { POST, buildTools } = await import("./route");

function ctx(projectId: string) {
  return { params: Promise.resolve({ projectId }) };
}

function jsonRequest(body: unknown): Request {
  return new Request("http://localhost:3001/api/agent/proj-1", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

describe("agent opening tools", () => {
  const OPENING_ID = "w:v:i:a>b@4.44:7.67-13.88#0.622";

  function makeFetch() {
    const calls: { path: string; method?: string; body?: string }[] = [];
    const fetchImpl = async (_userId: string, path: string, init?: RequestInit) => {
      calls.push({ path, method: init?.method, body: init?.body as string | undefined });
      return Response.json({ success: true });
    };
    return { calls, fetchImpl };
  }

  test("buildTools exposes the five opening tools on top of the original twelve", () => {
    const { fetchImpl } = makeFetch();
    const tools = buildTools("proj-1", "user-1", fetchImpl);
    const names = Object.keys(tools).sort();
    expect(names).toContain("list_openings");
    expect(names).toContain("add_door");
    expect(names).toContain("move_window");
    expect(names).toContain("resize_window");
    expect(names).toContain("remove_opening");
    expect(names).toHaveLength(17);
  });

  test("list_openings GETs the openings endpoint for the floor", async () => {
    const { calls, fetchImpl } = makeFetch();
    const tools = buildTools("proj-1", "user-1", fetchImpl);
    await tools.list_openings.execute?.({ floor: "gf" }, {} as never);
    expect(calls).toEqual([{ path: "projects/proj-1/openings?floor=gf" }]);
  });

  test("move_window POSTs an encoded id path with floor + along", async () => {
    const { calls, fetchImpl } = makeFetch();
    const tools = buildTools("proj-1", "user-1", fetchImpl);
    await tools.move_window.execute?.(
      { opening_id: OPENING_ID, floor: "ff", along: 2.4 },
      {} as never
    );
    expect(calls).toEqual([
      {
        path: `projects/proj-1/openings/${encodeURIComponent(OPENING_ID)}/move`,
        method: "POST",
        body: JSON.stringify({ floor: "ff", along: 2.4 }),
      },
    ]);
    expect(calls[0]?.path).not.toContain("#");
  });

  test("resize_window POSTs width", async () => {
    const { calls, fetchImpl } = makeFetch();
    const tools = buildTools("proj-1", "user-1", fetchImpl);
    await tools.resize_window.execute?.(
      { opening_id: OPENING_ID, floor: "gf", width: 0.75 },
      {} as never
    );
    expect(calls[0]?.path).toBe(
      `projects/proj-1/openings/${encodeURIComponent(OPENING_ID)}/resize`
    );
    expect(JSON.parse(calls[0]?.body ?? "null")).toEqual({ floor: "gf", width: 0.75 });
  });

  test("remove_opening DELETEs with the floor as a query param", async () => {
    const { calls, fetchImpl } = makeFetch();
    const tools = buildTools("proj-1", "user-1", fetchImpl);
    await tools.remove_opening.execute?.({ opening_id: OPENING_ID, floor: "gf" }, {} as never);
    expect(calls[0]?.method).toBe("DELETE");
    expect(calls[0]?.path).toBe(
      `projects/proj-1/openings/${encodeURIComponent(OPENING_ID)}?floor=gf`
    );
  });

  test("add_door posts the room pair and defaults", async () => {
    const { calls, fetchImpl } = makeFetch();
    const tools = buildTools("proj-1", "user-1", fetchImpl);
    await tools.add_door.execute?.(
      {
        floor: "gf",
        room_id: "c",
        to_room_id: "d",
        width: undefined,
        along: undefined,
        side: undefined,
      },
      {} as never
    );
    expect(calls[0]?.path).toBe("projects/proj-1/openings/doors");
    expect(JSON.parse(calls[0]?.body ?? "null")).toEqual({
      floor: "gf",
      room_id: "c",
      to_room_id: "d",
      width: undefined,
      along: undefined,
      side: undefined,
    });
  });

  test("a model-supplied slash in an opening id fails schema validation", () => {
    const { fetchImpl } = makeFetch();
    const tools = buildTools("proj-1", "user-1", fetchImpl);
    const parsed = tools.move_window.inputSchema.safeParse({
      opening_id: "../evil",
      floor: "gf",
      along: 1,
    });
    expect(parsed.success).toBe(false);
  });
});

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
