import { afterEach, beforeEach, describe, expect, mock, test } from "bun:test";
import { jwtVerify } from "jose";
import { fetchBackend } from "./backend-fetch";

const ORIGINAL_FETCH = global.fetch;
const ORIGINAL_SECRET = process.env.INTERNAL_AUTH_SECRET;
const ORIGINAL_SET_TIMEOUT = global.setTimeout;

describe("fetchBackend", () => {
  beforeEach(() => {
    process.env.INTERNAL_AUTH_SECRET = "test-secret-value-at-least-32-bytes-long";
  });

  afterEach(() => {
    global.fetch = ORIGINAL_FETCH;
    global.setTimeout = ORIGINAL_SET_TIMEOUT;
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

  test("wires an AbortSignal so a hung backend fails fast instead of blocking forever", async () => {
    let capturedSignal: AbortSignal | undefined;
    global.fetch = mock(async (_url: string | URL, init?: RequestInit) => {
      capturedSignal = init?.signal ?? undefined;
      return new Response("{}");
    }) as typeof fetch;

    await fetchBackend("user-1", "projects");

    expect(capturedSignal).toBeInstanceOf(AbortSignal);
    expect(capturedSignal?.aborted).toBe(false);
  });

  test("combines a caller-supplied signal with the timeout signal so both can abort", async () => {
    let capturedSignal: AbortSignal | undefined;
    global.fetch = mock(async (_url: string | URL, init?: RequestInit) => {
      capturedSignal = init?.signal ?? undefined;
      return new Response("{}");
    }) as typeof fetch;

    const callerController = new AbortController();
    await fetchBackend("user-1", "projects", { signal: callerController.signal });

    // The combined signal is NOT the caller's own — otherwise the timeout could
    // never fire. Aborting the caller's controller still aborts the combination.
    expect(capturedSignal).toBeInstanceOf(AbortSignal);
    expect(capturedSignal).not.toBe(callerController.signal);
    expect(capturedSignal?.aborted).toBe(false);
    callerController.abort();
    expect(capturedSignal?.aborted).toBe(true);
  });

  test("a hung backend aborts after a short timeoutMs even with no caller signal", async () => {
    global.fetch = mock((_url: string | URL, init?: RequestInit) => {
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("The operation was aborted", "AbortError"));
        });
      });
    }) as typeof fetch;

    await expect(fetchBackend("user-1", "projects", { timeoutMs: 30 })).rejects.toThrow();
  });

  test("timeoutMs still fires when a caller signal is supplied that never aborts", async () => {
    global.fetch = mock((_url: string | URL, init?: RequestInit) => {
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("The operation was aborted", "AbortError"));
        });
      });
    }) as typeof fetch;

    const neverAborts = new AbortController();
    await expect(
      fetchBackend("user-1", "projects", { signal: neverAborts.signal, timeoutMs: 30 })
    ).rejects.toThrow();
  });

  test("applies the default 15s timeout when none is specified", async () => {
    const delays: number[] = [];
    global.setTimeout = ((fn: () => void, delay?: number) => {
      delays.push(delay ?? 0);
      return ORIGINAL_SET_TIMEOUT(fn, delay);
    }) as typeof setTimeout;
    global.fetch = mock(async () => new Response("{}")) as typeof fetch;

    await fetchBackend("user-1", "projects");

    expect(delays.at(-1)).toBe(15_000);
  });

  test("honors a custom timeoutMs for slow paths", async () => {
    const delays: number[] = [];
    global.setTimeout = ((fn: () => void, delay?: number) => {
      delays.push(delay ?? 0);
      return ORIGINAL_SET_TIMEOUT(fn, delay);
    }) as typeof setTimeout;
    global.fetch = mock(async () => new Response("{}")) as typeof fetch;

    await fetchBackend("user-1", "projects", { timeoutMs: 45_000 });

    expect(delays.at(-1)).toBe(45_000);
  });

  test("does not forward timeoutMs into the fetch RequestInit", async () => {
    let capturedInit: RequestInit | undefined;
    global.fetch = mock(async (_url: string | URL, init?: RequestInit) => {
      capturedInit = init;
      return new Response("{}");
    }) as typeof fetch;

    await fetchBackend("user-1", "projects", { timeoutMs: 45_000, method: "POST" });

    expect(capturedInit?.method).toBe("POST");
    expect((capturedInit as Record<string, unknown>)?.timeoutMs).toBeUndefined();
  });
});
