import { describe, expect, test } from "bun:test";
import { localeCookieToWhisperLanguage } from "./route";

describe("localeCookieToWhisperLanguage", () => {
  test("maps ta cookie to ta", () => expect(localeCookieToWhisperLanguage("ta")).toBe("ta"));
  test("maps hi cookie to hi", () => expect(localeCookieToWhisperLanguage("hi")).toBe("hi"));
  test("maps en cookie to en", () => expect(localeCookieToWhisperLanguage("en")).toBe("en"));
  test("defaults to en when cookie missing", () =>
    expect(localeCookieToWhisperLanguage(undefined)).toBe("en"));
  test("defaults to en when cookie value is malformed", () =>
    expect(localeCookieToWhisperLanguage("fr")).toBe("en"));
  test("defaults to en when cookie value is empty string", () =>
    expect(localeCookieToWhisperLanguage("")).toBe("en"));
});
