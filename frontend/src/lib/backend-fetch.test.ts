import { afterEach, beforeEach, describe, expect, mock, test } from "bun:test";
import { jwtVerify } from "jose";
import { fetchBackend } from "./backend-fetch";

const ORIGINAL_FETCH = global.fetch;
const ORIGINAL_SECRET = process.env.INTERNAL_AUTH_SECRET;

describe("fetchBackend", () => {
  beforeEach(() => {
    process.env.INTERNAL_AUTH_SECRET = "test-secret-value-at-least-32-bytes-long";
  });

  afterEach(() => {
    global.fetch = ORIGINAL_FETCH;
    process.env.INTERNAL_AUTH_SECRET = ORIGINAL_SECRET;
  });

  test("throws when INTERNAL_AUTH_SECRET is unset, without calling fetch", async () => {
    process.env.INTERNAL_AUTH_SECRET = "";
    let fetchCalled = false;
    global.fetch = mock(async () => {
      fetchCalled = true;
      return new Response("{}");
    }) as typeof fetch;

    await expect(fetchBackend("user-1", "projects")).rejects.toThrow(
      "INTERNAL_AUTH_SECRET is not set"
    );
    expect(fetchCalled).toBe(false);
  });

  test("targets BACKEND_URL, strips a leading slash from path, and mints a token for the given user", async () => {
    let capturedUrl: string | undefined;
    let capturedHeaders: Headers | undefined;
    global.fetch = mock(async (url: string | URL, init?: RequestInit) => {
      capturedUrl = url.toString();
      capturedHeaders = new Headers(init?.headers);
      return new Response("{}");
    }) as typeof fetch;

    await fetchBackend("user-42", "/projects/p1/rooms");

    expect(capturedUrl).toBe("http://localhost:8000/api/projects/p1/rooms");
    const token = capturedHeaders?.get("x-internal-auth") ?? "";
    const { payload } = await jwtVerify(
      token,
      new TextEncoder().encode(process.env.INTERNAL_AUTH_SECRET)
    );
    expect(payload.user_id).toBe("user-42");
  });

  test("sets X-Internal-Auth and defaults Content-Type when no headers are given", async () => {
    let capturedHeaders: Headers | undefined;
    global.fetch = mock(async (_url: string | URL, init?: RequestInit) => {
      capturedHeaders = new Headers(init?.headers);
      return new Response("{}");
    }) as typeof fetch;

    await fetchBackend("user-1", "projects");

    expect(capturedHeaders?.get("x-internal-auth")).toBeTruthy();
    expect(capturedHeaders?.get("content-type")).toBe("application/json");
  });

  test("preserves a caller-supplied plain-object Content-Type instead of overwriting it", async () => {
    let capturedHeaders: Headers | undefined;
    global.fetch = mock(async (_url: string | URL, init?: RequestInit) => {
      capturedHeaders = new Headers(init?.headers);
      return new Response("{}");
    }) as typeof fetch;

    await fetchBackend("user-1", "projects", {
      headers: { "Content-Type": "text/plain" },
    });

    expect(capturedHeaders?.get("content-type")).toBe("text/plain");
  });

  test("correctly merges headers passed as a real Headers instance, not just a plain object", async () => {
    let capturedHeaders: Headers | undefined;
    global.fetch = mock(async (_url: string | URL, init?: RequestInit) => {
      capturedHeaders = new Headers(init?.headers);
      return new Response("{}");
    }) as typeof fetch;

    const callerHeaders = new Headers({ "X-Project-Id": "p1" });
    await fetchBackend("user-1", "projects", { headers: callerHeaders });

    expect(capturedHeaders?.get("x-project-id")).toBe("p1");
    expect(capturedHeaders?.get("x-internal-auth")).toBeTruthy();
  });

  test("correctly merges headers passed as a tuple array", async () => {
    let capturedHeaders: Headers | undefined;
    global.fetch = mock(async (_url: string | URL, init?: RequestInit) => {
      capturedHeaders = new Headers(init?.headers);
      return new Response("{}");
    }) as typeof fetch;

    await fetchBackend("user-1", "projects", {
      headers: [["X-Project-Id", "p1"]],
    });

    expect(capturedHeaders?.get("x-project-id")).toBe("p1");
  });

  test("forwards method and body through unchanged", async () => {
    let capturedMethod: string | undefined;
    let capturedBody: string | undefined;
    global.fetch = mock(async (_url: string | URL, init?: RequestInit) => {
      capturedMethod = init?.method;
      capturedBody = init?.body as string;
      return new Response("{}");
    }) as typeof fetch;

    await fetchBackend("user-1", "projects", {
      method: "POST",
      body: JSON.stringify({ name: "Test" }),
    });

    expect(capturedMethod).toBe("POST");
    expect(capturedBody).toBe(JSON.stringify({ name: "Test" }));
  });
});
