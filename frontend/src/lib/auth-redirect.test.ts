import { describe, expect, it } from "bun:test";
import { resolveAuthenticatedRedirect } from "./auth-redirect";

describe("resolveAuthenticatedRedirect", () => {
  it("sends an already-signed-in user with a template param to /projects/new with the template preserved", () => {
    const params = new URLSearchParams("template=abc123");
    expect(resolveAuthenticatedRedirect(params)).toBe("/projects/new?template=abc123");
  });

  it("falls back to /dashboard when there is no template param", () => {
    expect(resolveAuthenticatedRedirect(new URLSearchParams())).toBe("/dashboard");
  });

  it("encodes template values that contain URL-unsafe characters", () => {
    const params = new URLSearchParams();
    params.set("template", "a b&c");
    expect(resolveAuthenticatedRedirect(params)).toBe("/projects/new?template=a%20b%26c");
  });
});
