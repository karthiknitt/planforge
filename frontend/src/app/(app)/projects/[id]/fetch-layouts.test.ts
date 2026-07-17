import { afterEach, beforeEach, describe, expect, mock, test } from "bun:test";

/**
 * Fake unstable_cache with real Next semantics: fulfilled values are cached
 * per key, rejections are NOT cached (the error propagates and nothing is
 * stored). This is exactly the property the negative-caching regression
 * relies on — a transient backend failure must not be served for 5 minutes.
 */
const cacheStore = new Map<string, unknown>();

mock.module("next/cache", () => ({
  unstable_cache: <T>(fn: () => Promise<T>, keys: string[]) => {
    const key = JSON.stringify(keys);
    return async (): Promise<T> => {
      if (cacheStore.has(key)) return cacheStore.get(key) as T;
      const value = await fn();
      cacheStore.set(key, value);
      return value;
    };
  },
  revalidatePath: () => undefined,
  revalidateTag: () => undefined,
}));

const { fetchLayouts } = await import("./fetch-layouts");

const ORIGINAL_FETCH = global.fetch;
const ORIGINAL_SECRET = process.env.INTERNAL_AUTH_SECRET;

const OK_BODY = JSON.stringify({ project_id: "p1", layouts: [] });

describe("fetchLayouts", () => {
  beforeEach(() => {
    process.env.INTERNAL_AUTH_SECRET = "test-secret-value-at-least-32-bytes-long";
    cacheStore.clear();
  });

  afterEach(() => {
    global.fetch = ORIGINAL_FETCH;
    process.env.INTERNAL_AUTH_SECRET = ORIGINAL_SECRET;
  });

  test("returns parsed layouts on success and caches the result", async () => {
    let calls = 0;
    global.fetch = mock(async () => {
      calls++;
      return new Response(OK_BODY, { status: 200 });
    }) as typeof fetch;

    const first = await fetchLayouts("p1", "u1");
    const second = await fetchLayouts("p1", "u1");

    expect(first?.layouts).toEqual([]);
    expect(second?.layouts).toEqual([]);
    expect(calls).toBe(1);
  });

  test("returns null on a backend error response without throwing", async () => {
    global.fetch = mock(async () => new Response("boom", { status: 503 })) as typeof fetch;

    expect(await fetchLayouts("p1", "u1")).toBeNull();
  });

  test("returns null on a network failure without throwing", async () => {
    global.fetch = mock(async () => {
      throw new Error("ECONNREFUSED");
    }) as typeof fetch;

    expect(await fetchLayouts("p1", "u1")).toBeNull();
  });

  test("does NOT cache failures — a request after a transient failure recovers", async () => {
    let calls = 0;
    global.fetch = mock(async () => {
      calls++;
      if (calls === 1) return new Response("cold start", { status: 503 });
      return new Response(OK_BODY, { status: 200 });
    }) as typeof fetch;

    expect(await fetchLayouts("p1", "u1")).toBeNull();
    const recovered = await fetchLayouts("p1", "u1");

    expect(recovered).not.toBeNull();
    expect(recovered?.layouts).toEqual([]);
    expect(calls).toBe(2);
  });

  test("cache key isolates users — one user's cached result is not served to another", async () => {
    let calls = 0;
    global.fetch = mock(async () => {
      calls++;
      return new Response(OK_BODY, { status: 200 });
    }) as typeof fetch;

    await fetchLayouts("p1", "u1");
    await fetchLayouts("p1", "u2");

    expect(calls).toBe(2);
  });
});
