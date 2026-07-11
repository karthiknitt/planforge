import { describe, expect, test } from "bun:test";
import {
  AGENT_TOOL_TIMEOUT_MS,
  callBackendTool,
  NO_LAYOUTS_TOOL_RESULT,
  roomIdSchema,
} from "./agent-backend-tool";
import type { FetchBackendInit } from "./backend-fetch";

// A stub standing in for fetchBackend: records the init it was called with and
// returns a caller-chosen Response, so callBackendTool's branching can be
// exercised without minting JWTs or hitting the network.
function stubFetch(response: Response) {
  const calls: { userId: string; path: string; init?: FetchBackendInit }[] = [];
  const fn = (userId: string, path: string, init?: FetchBackendInit) => {
    calls.push({ userId, path, init });
    return Promise.resolve(response);
  };
  return { fn, calls };
}

describe("callBackendTool", () => {
  test("409 {detail:{code:'no_layouts'}} returns the conversational no-layouts string", async () => {
    const { fn } = stubFetch(
      new Response(JSON.stringify({ detail: { code: "no_layouts" } }), { status: 409 })
    );
    const result = await callBackendTool("user-1", "projects/p1/rooms", undefined, fn);
    expect(result).toBe(NO_LAYOUTS_TOOL_RESULT);
  });

  test("409 with a different JSON detail returns the parsed body unchanged (pinned)", async () => {
    const body = { detail: { code: "overlap", message: "rooms overlap" } };
    const { fn } = stubFetch(new Response(JSON.stringify(body), { status: 409 }));
    const result = await callBackendTool("user-1", "projects/p1/rooms/r1/move", undefined, fn);
    expect(result).toEqual(body);
  });

  test("409 with a non-JSON body returns the generic conflict object (pinned)", async () => {
    const { fn } = stubFetch(new Response("not json", { status: 409 }));
    const result = await callBackendTool("user-1", "projects/p1/rooms", undefined, fn);
    expect(result).toEqual({ error: "Request conflicts with the current layout state" });
  });

  test("a 200 OK JSON response is returned parsed (happy path)", async () => {
    const rooms = { rooms: [{ id: "r1", type: "bedroom" }] };
    const { fn } = stubFetch(new Response(JSON.stringify(rooms), { status: 200 }));
    const result = await callBackendTool("user-1", "projects/p1/rooms", undefined, fn);
    expect(result).toEqual(rooms);
  });

  // PINNED behaviour: a non-409 error with a non-JSON body lets res.json() throw.
  // This is deliberately safe — ai@6's executeToolCall catches a thrown tool
  // execute and converts it into a `tool-error` part the model can recover from
  // (verified against ai@6.0.116 dist), so it never crashes the assistant stream.
  test("a 500 with a non-JSON body throws (ai@6 executeToolCall turns it into a tool-error part)", async () => {
    const { fn } = stubFetch(new Response("Internal Server Error", { status: 500 }));
    await expect(callBackendTool("user-1", "projects/p1/rooms", undefined, fn)).rejects.toThrow();
  });

  test("applies the 45s agent-tool timeout on every backend call", async () => {
    const { fn, calls } = stubFetch(new Response("{}", { status: 200 }));
    await callBackendTool("user-1", "projects/p1/rooms", { method: "POST" }, fn);
    expect(calls[0]?.init?.timeoutMs).toBe(AGENT_TOOL_TIMEOUT_MS);
    expect(calls[0]?.init?.method).toBe("POST");
  });
});

describe("roomIdSchema", () => {
  test("accepts normal room identifiers", () => {
    expect(roomIdSchema.safeParse("bedroom_1").success).toBe(true);
    expect(roomIdSchema.safeParse("GF-Room-2").success).toBe(true);
    expect(roomIdSchema.safeParse("r1").success).toBe(true);
  });

  test("rejects path-traversal and slash-bearing values", () => {
    expect(roomIdSchema.safeParse("../projects").success).toBe(false);
    expect(roomIdSchema.safeParse("a/b").success).toBe(false);
    expect(roomIdSchema.safeParse("room 1").success).toBe(false);
    expect(roomIdSchema.safeParse("room.1").success).toBe(false);
    expect(roomIdSchema.safeParse("").success).toBe(false);
  });
});
