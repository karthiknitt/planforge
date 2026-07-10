import { describe, expect, it } from "bun:test";
import { buildRenderImageUrl, classifyRenderStatus } from "./render-tab";

describe("buildRenderImageUrl", () => {
  it("builds the GET render URL with a cache-busting version param", () => {
    expect(buildRenderImageUrl("proj-1", "A", 0)).toBe(
      "/api/backend/projects/proj-1/layouts/A/render?v=0"
    );
    expect(buildRenderImageUrl("proj-1", "A", 3)).toBe(
      "/api/backend/projects/proj-1/layouts/A/render?v=3"
    );
  });

  it("encodes projectId and layoutKey so special characters can't break the path", () => {
    expect(buildRenderImageUrl("proj 1", "A/B", 0)).toBe(
      "/api/backend/projects/proj%201/layouts/A%2FB/render?v=0"
    );
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
