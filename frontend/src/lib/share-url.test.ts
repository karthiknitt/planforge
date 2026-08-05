import { describe, expect, it } from "bun:test";
import { buildShareUrl, buildWhatsAppMessage, buildWhatsAppShareLink } from "./share-url";

describe("buildShareUrl", () => {
  it("joins origin and the backend-provided share path", () => {
    expect(buildShareUrl("https://planforge.app", "/share/abc123")).toBe(
      "https://planforge.app/share/abc123"
    );
  });

  it("does not double up slashes when origin has a trailing slash", () => {
    expect(buildShareUrl("https://planforge.app/", "/share/abc123")).toBe(
      "https://planforge.app/share/abc123"
    );
  });
});

describe("buildWhatsAppMessage", () => {
  it("includes the project name, layout id, and public share URL", () => {
    const msg = buildWhatsAppMessage("Kumar Residence", "2", "https://planforge.app/share/abc123");
    expect(msg).toBe(
      "Check out this floor plan for Kumar Residence (Layout 2): https://planforge.app/share/abc123"
    );
  });

  it("never embeds a login-walled app URL", () => {
    const msg = buildWhatsAppMessage("X", "1", "https://planforge.app/share/tok");
    expect(msg).not.toContain("/projects/");
    expect(msg).not.toContain("/dashboard");
  });
});

describe("buildWhatsAppShareLink", () => {
  it("URL-encodes the message text into a wa.me link", () => {
    const link = buildWhatsAppShareLink("Hello: world?");
    expect(link).toBe(`https://wa.me/?text=${encodeURIComponent("Hello: world?")}`);
  });
});
