import { afterEach, beforeEach, describe, expect, mock, test } from "bun:test";
import { fetchProjectLayoutMap } from "./fetch-project-layout-map";

const ORIGINAL_FETCH = global.fetch;
const ORIGINAL_SECRET = process.env.INTERNAL_AUTH_SECRET;

describe("fetchProjectLayoutMap", () => {
  beforeEach(() => {
    process.env.INTERNAL_AUTH_SECRET = "test-secret-value-at-least-32-bytes-long";
  });

  afterEach(() => {
    global.fetch = ORIGINAL_FETCH;
    process.env.INTERNAL_AUTH_SECRET = ORIGINAL_SECRET;
  });

  test("maps each project id to its has_layouts flag", async () => {
    global.fetch = mock(
      async () =>
        new Response(
          JSON.stringify([
            { id: "p1", has_layouts: true },
            { id: "p2", has_layouts: false },
          ])
        )
    ) as typeof fetch;

    const map = await fetchProjectLayoutMap("user-1");
    expect(map).toEqual({ p1: true, p2: false });
  });

  test("treats a missing has_layouts field as false, not omitted", async () => {
    global.fetch = mock(async () => new Response(JSON.stringify([{ id: "p1" }]))) as typeof fetch;

    const map = await fetchProjectLayoutMap("user-1");
    expect(map).toEqual({ p1: false });
  });

  test("skips entries without an id", async () => {
    global.fetch = mock(
      async () => new Response(JSON.stringify([{ has_layouts: true }, { id: "p2" }]))
    ) as typeof fetch;

    const map = await fetchProjectLayoutMap("user-1");
    expect(map).toEqual({ p2: false });
  });

  test("falls back to an empty map on a non-OK response", async () => {
    global.fetch = mock(async () => new Response("nope", { status: 500 })) as typeof fetch;

    const map = await fetchProjectLayoutMap("user-1");
    expect(map).toEqual({});
  });

  test("falls back to an empty map when fetch throws (e.g. cold-start timeout)", async () => {
    global.fetch = mock(async () => {
      throw new Error("network error");
    }) as typeof fetch;

    const map = await fetchProjectLayoutMap("user-1");
    expect(map).toEqual({});
  });
});
