import { afterEach, beforeEach, describe, expect, mock, test } from "bun:test";
import { NextRequest } from "next/server";

import { getSessionMock } from "@/test/setup";

const { GET, POST } = await import("./route");

const ORIGINAL_FETCH = global.fetch;
const ORIGINAL_SECRET = process.env.INTERNAL_AUTH_SECRET;

function ctx(path: string[]) {
  return { params: Promise.resolve({ path }) };
}

describe("backend proxy route", () => {
  beforeEach(() => {
    process.env.INTERNAL_AUTH_SECRET = "test-secret-value-at-least-32-bytes-long";
    getSessionMock.mockReset();
  });

  afterEach(() => {
    global.fetch = ORIGINAL_FETCH;
    process.env.INTERNAL_AUTH_SECRET = ORIGINAL_SECRET;
  });

  test("returns 401 when there is no session", async () => {
    getSessionMock.mockImplementation(async () => null);
    const req = new NextRequest("http://localhost:3001/api/backend/projects");
    const res = await GET(req, ctx(["projects"]));
    expect(res.status).toBe(401);
  });

  test("returns 500 without leaking details when session retrieval throws", async () => {
    getSessionMock.mockImplementation(async () => {
      throw new Error("db connection refused: password=super-secret");
    });
    const req = new NextRequest("http://localhost:3001/api/backend/projects");
    const res = await GET(req, ctx(["projects"]));
    expect(res.status).toBe(500);
    const body = await res.text();
    expect(body).not.toContain("super-secret");
  });

  test("forwards to the backend with a minted token and passes through a successful response", async () => {
    getSessionMock.mockImplementation(async () => ({ user: { id: "user-42" } }));
    let capturedUrl: string | undefined;
    let capturedHeaders: Headers | undefined;
    global.fetch = mock(async (url: string | URL, init?: RequestInit) => {
      capturedUrl = url.toString();
      capturedHeaders = new Headers(init?.headers as HeadersInit);
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof fetch;

    const req = new NextRequest("http://localhost:3001/api/backend/projects/p1/rooms", {
      headers: { "X-Project-Id": "p1" },
    });
    const res = await GET(req, ctx(["projects", "p1", "rooms"]));

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true });
    expect(capturedUrl).toBe("http://localhost:8000/api/projects/p1/rooms");
    expect(capturedHeaders?.get("x-internal-auth")).toBeTruthy();
    expect(capturedHeaders?.get("x-project-id")).toBe("p1");
  });

  test("a client-supplied X-Internal-Auth header is never forwarded to the backend", async () => {
    getSessionMock.mockImplementation(async () => ({ user: { id: "user-42" } }));
    let capturedHeaders: Headers | undefined;
    global.fetch = mock(async (_url: string | URL, init?: RequestInit) => {
      capturedHeaders = new Headers(init?.headers as HeadersInit);
      return new Response("{}", { status: 200 });
    }) as typeof fetch;

    const req = new NextRequest("http://localhost:3001/api/backend/projects", {
      headers: { "X-Internal-Auth": "attacker-forged-token" },
    });
    await GET(req, ctx(["projects"]));

    expect(capturedHeaders?.get("x-internal-auth")).not.toBe("attacker-forged-token");
  });

  test("returns 503 without leaking details when the backend is unreachable", async () => {
    getSessionMock.mockImplementation(async () => ({ user: { id: "user-42" } }));
    global.fetch = mock(async () => {
      throw new Error("connect ECONNREFUSED 10.0.0.5:8000");
    }) as typeof fetch;

    const req = new NextRequest("http://localhost:3001/api/backend/projects");
    const res = await GET(req, ctx(["projects"]));
    expect(res.status).toBe(503);
    const body = await res.text();
    expect(body).not.toContain("10.0.0.5");
  });

  test("throws loudly at request time if INTERNAL_AUTH_SECRET is unset (fail-fast on misconfiguration)", async () => {
    getSessionMock.mockImplementation(async () => ({ user: { id: "user-42" } }));
    process.env.INTERNAL_AUTH_SECRET = "";
    const req = new NextRequest("http://localhost:3001/api/backend/projects");
    await expect(GET(req, ctx(["projects"]))).rejects.toThrow("INTERNAL_AUTH_SECRET is not set");
  });

  test("forwards a POST body and method through unchanged", async () => {
    getSessionMock.mockImplementation(async () => ({ user: { id: "user-42" } }));
    let capturedMethod: string | undefined;
    let capturedBody: string | undefined;
    global.fetch = mock(async (_url: string | URL, init?: RequestInit) => {
      capturedMethod = init?.method;
      capturedBody = init?.body ? Buffer.from(init.body as ArrayBuffer).toString() : undefined;
      return new Response("{}", { status: 201 });
    }) as typeof fetch;

    const req = new NextRequest("http://localhost:3001/api/backend/projects", {
      method: "POST",
      body: JSON.stringify({ name: "Test" }),
    });
    const res = await POST(req, ctx(["projects"]));

    expect(res.status).toBe(201);
    expect(capturedMethod).toBe("POST");
    expect(capturedBody).toBe(JSON.stringify({ name: "Test" }));
  });
});
