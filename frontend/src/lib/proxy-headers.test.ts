import { describe, expect, test } from "bun:test";
import { forwardableHeaders, HEADER_BLOCKLIST } from "./proxy-headers";

describe("forwardableHeaders", () => {
  test("passes through an ordinary custom header", () => {
    const headers = new Headers({ "X-Project-Id": "proj-123" });
    expect(forwardableHeaders(headers)["x-project-id"]).toBe("proj-123");
  });

  test("strips every header on the blocklist, case-insensitively", () => {
    const headers = new Headers({
      Host: "evil.example.com",
      Connection: "keep-alive",
      "Content-Length": "9999",
      Cookie: "session=super-secret",
      "X-Internal-Auth": "forged-token",
      "Transfer-Encoding": "chunked",
      TE: "trailers",
    });
    const result = forwardableHeaders(headers);
    for (const blocked of HEADER_BLOCKLIST) {
      expect(result[blocked]).toBeUndefined();
    }
  });

  test("a client cannot forge X-Internal-Auth to bypass the proxy's own token", () => {
    const headers = new Headers({ "X-Internal-Auth": "attacker-supplied-token" });
    expect(forwardableHeaders(headers)["x-internal-auth"]).toBeUndefined();
  });

  test("defaults Content-Type to application/json when absent", () => {
    const headers = new Headers();
    expect(forwardableHeaders(headers)["Content-Type"]).toBe("application/json");
  });

  test("preserves an explicit Content-Type instead of overwriting it", () => {
    const headers = new Headers({ "Content-Type": "multipart/form-data" });
    const result = forwardableHeaders(headers);
    expect(result["content-type"]).toBe("multipart/form-data");
    expect(result["Content-Type"]).toBeUndefined();
  });
});
