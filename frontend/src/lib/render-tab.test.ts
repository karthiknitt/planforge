import { describe, expect, it } from "bun:test";
import { buildRenderImageUrl, classifyRenderStatus, floorKeyFromIndex } from "./render-tab";

describe("buildRenderImageUrl", () => {
  it("builds the GET render URL with floor + cache-busting version params", () => {
    expect(buildRenderImageUrl("proj-1", "A", 0)).toBe(
      "/api/backend/projects/proj-1/layouts/A/render?floor=ground_floor&v=0"
    );
    expect(buildRenderImageUrl("proj-1", "A", 3, "first_floor")).toBe(
      "/api/backend/projects/proj-1/layouts/A/render?floor=first_floor&v=3"
    );
  });

  it("encodes projectId and layoutKey so special characters can't break the path", () => {
    expect(buildRenderImageUrl("proj 1", "A/B", 0)).toBe(
      "/api/backend/projects/proj%201/layouts/A%2FB/render?floor=ground_floor&v=0"
    );
  });
});

describe("floorKeyFromIndex", () => {
  it("maps viewer floor indices to geometry dict keys", () => {
    expect(floorKeyFromIndex(-1)).toBe("basement_floor");
    expect(floorKeyFromIndex(0)).toBe("ground_floor");
    expect(floorKeyFromIndex(1)).toBe("first_floor");
    expect(floorKeyFromIndex(2)).toBe("second_floor");
  });

  it("falls back to ground floor for unknown indices", () => {
    expect(floorKeyFromIndex(99)).toBe("ground_floor");
  });
});

describe("classifyRenderStatus", () => {
  it("classifies 2xx as ready", () => {
    expect(classifyRenderStatus(200)).toBe("ready");
    expect(classifyRenderStatus(201)).toBe("ready");
  });

  it("classifies 402 as upsell", () => {
    expect(classifyRenderStatus(402)).toBe("upsell");
  });

  it("classifies 503 as unavailable", () => {
    expect(classifyRenderStatus(503)).toBe("unavailable");
  });

  it("classifies anything else (502, network-style codes, 500) as error", () => {
    expect(classifyRenderStatus(502)).toBe("error");
    expect(classifyRenderStatus(500)).toBe("error");
    expect(classifyRenderStatus(404)).toBe("error");
  });
});
