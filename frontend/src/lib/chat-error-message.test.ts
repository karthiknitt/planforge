import { describe, expect, test } from "bun:test";
import { friendlyChatError } from "./chat-error-message";

describe("friendlyChatError", () => {
  test("maps a 401 JSON response body to a session/auth message", () => {
    const err = new Error('{"error":"Unauthorized"}');
    expect(friendlyChatError(err)).toEqual({
      title: "Session expired",
      detail: "Sign in again",
    });
  });

  test("maps a message containing 'unauthorized' to a session/auth message", () => {
    const err = new Error("401 Unauthorized: no session cookie");
    expect(friendlyChatError(err).title).toBe("Session expired");
  });

  test("maps a statusCode 401 property to a session/auth message", () => {
    const err = Object.assign(new Error("failed"), { statusCode: 401 });
    expect(friendlyChatError(err)).toEqual({
      title: "Session expired",
      detail: "Sign in again",
    });
  });

  test("maps a 403/pro-gated response body to a Pro plan required message", () => {
    const err = new Error('{"error":"Forbidden: Pro plan required"}');
    expect(friendlyChatError(err)).toEqual({
      title: "Pro plan required for agent chat",
    });
  });

  test("maps a statusCode 403 property to a Pro plan required message", () => {
    const err = Object.assign(new Error("forbidden"), { statusCode: 403 });
    expect(friendlyChatError(err)).toEqual({
      title: "Pro plan required for agent chat",
    });
  });

  test("maps an AbortError to a cold-start/timeout message", () => {
    const err = new DOMException("The operation was aborted.", "AbortError");
    expect(friendlyChatError(err)).toEqual({
      title: "Backend timed out — it may be cold-starting; try again in ~30s",
    });
  });

  test("maps a message mentioning 'timed out' to the same cold-start message", () => {
    const err = new Error("Request timed out after 60000ms");
    expect(friendlyChatError(err)).toEqual({
      title: "Backend timed out — it may be cold-starting; try again in ~30s",
    });
  });

  test("passes through an unrecognized error's message as detail with a generic title", () => {
    const err = new Error("Anthropic: model not found; OpenAI: invalid API key");
    expect(friendlyChatError(err)).toEqual({
      title: "Something went wrong",
      detail: "Anthropic: model not found; OpenAI: invalid API key",
    });
  });

  test("passes through a plain string error as detail", () => {
    expect(friendlyChatError("network down")).toEqual({
      title: "Something went wrong",
      detail: "network down",
    });
  });

  test("does not crash on non-Error input and returns a safe generic result", () => {
    expect(friendlyChatError(undefined)).toEqual({ title: "Something went wrong" });
    expect(friendlyChatError(null)).toEqual({ title: "Something went wrong" });
    expect(friendlyChatError(42)).toEqual({ title: "Something went wrong" });
    expect(friendlyChatError({ some: "object" })).toEqual({ title: "Something went wrong" });
  });
});
