import { describe, expect, test } from "bun:test";
import { describeProviderError, shouldFallback } from "./agent-errors";

function apiError(message: string, statusCode?: number): Error {
  const err = new Error(message) as Error & { statusCode?: number };
  if (statusCode !== undefined) {
    err.statusCode = statusCode;
  }
  return err;
}

describe("shouldFallback", () => {
  test("falls back on an Anthropic 404 not_found_error for an invalid model", () => {
    const err = apiError(
      'model: claude-sonnet-4-6 not found {"type":"error","error":{"type":"not_found_error","message":"model: claude-sonnet-4-6"}}',
      404
    );
    expect(shouldFallback(err)).toBe(true);
  });

  test("falls back on a billing/insufficient-credit error", () => {
    expect(shouldFallback(apiError("Your account has insufficient credit balance", 402))).toBe(
      true
    );
  });

  test("falls back on a 429 rate limit error", () => {
    expect(shouldFallback(apiError("rate_limit_error: too many requests", 429))).toBe(true);
  });

  test("falls back on a network fetch failure", () => {
    expect(shouldFallback(new TypeError("fetch failed"))).toBe(true);
    expect(shouldFallback(new Error("connect ECONNREFUSED 127.0.0.1:443"))).toBe(true);
  });

  test("falls back on an invalid API key 401 (the next provider may still work)", () => {
    expect(shouldFallback(apiError("401 Unauthorized: invalid x-api-key", 401))).toBe(true);
  });

  test("does not fall back on a content-policy refusal", () => {
    expect(
      shouldFallback(apiError("stop_reason: refusal - request declined for safety reasons"))
    ).toBe(false);
  });

  test("does not fall back on a generic application logic error", () => {
    expect(shouldFallback(new Error("Room not found in current layout"))).toBe(false);
    expect(shouldFallback(new TypeError("Cannot read properties of undefined (reading 'x')"))).toBe(
      false
    );
  });

  test("does not crash on unknown non-Error values and returns a boolean", () => {
    expect(shouldFallback(undefined)).toBe(false);
    expect(shouldFallback(null)).toBe(false);
    expect(shouldFallback(42)).toBe(false);
    expect(shouldFallback("plain string error")).toBe(false);
    expect(shouldFallback({ some: "object" })).toBe(false);
  });
});

describe("describeProviderError", () => {
  test("labels a model-not-found error clearly", () => {
    const err = apiError("model: claude-sonnet-4-6 not found", 404);
    expect(describeProviderError(err, "Anthropic")).toBe("Anthropic: model not found");
  });

  test("labels an invalid API key error clearly", () => {
    const err = apiError("401 Unauthorized: invalid x-api-key", 401);
    expect(describeProviderError(err, "OpenAI")).toBe("OpenAI: invalid API key");
  });

  test("labels a billing error clearly", () => {
    const err = apiError("insufficient credit balance", 402);
    expect(describeProviderError(err, "Anthropic")).toBe("Anthropic: billing/insufficient credit");
  });

  test("labels a rate limit error clearly", () => {
    const err = apiError("rate_limit_error", 429);
    expect(describeProviderError(err, "OpenRouter")).toBe("OpenRouter: rate limited");
  });

  test("labels a network error clearly", () => {
    expect(describeProviderError(new TypeError("fetch failed"), "OpenAI")).toBe(
      "OpenAI: network/connection error"
    );
  });

  test("falls back to a truncated message for unrecognized errors", () => {
    const result = describeProviderError(new Error("some unusual failure"), "Anthropic");
    expect(result).toBe("Anthropic: some unusual failure");
  });

  test("does not crash on unknown non-Error values", () => {
    expect(() => describeProviderError(undefined, "Anthropic")).not.toThrow();
    expect(() => describeProviderError(null, "Anthropic")).not.toThrow();
  });
});
