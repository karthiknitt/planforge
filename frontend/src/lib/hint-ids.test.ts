import { describe, expect, test } from "bun:test";
import { HINT_IDS, isHintId, parseDismissedHints } from "./hint-ids";

describe("isHintId", () => {
  test("accepts every known id", () => {
    for (const id of HINT_IDS) expect(isHintId(id)).toBe(true);
  });
  test("rejects unknown strings", () => expect(isHintId("bogus")).toBe(false));
  test("rejects non-strings", () => expect(isHintId(42)).toBe(false));
});

describe("parseDismissedHints", () => {
  test("parses a valid JSON array", () =>
    expect(parseDismissedHints('["chat","compare"]')).toEqual(["chat", "compare"]));
  test("drops unknown ids from an otherwise valid array", () =>
    expect(parseDismissedHints('["chat","nonsense"]')).toEqual(["chat"]));
  test("returns [] for null", () => expect(parseDismissedHints(null)).toEqual([]));
  test("returns [] for undefined", () => expect(parseDismissedHints(undefined)).toEqual([]));
  test("returns [] for empty string", () => expect(parseDismissedHints("")).toEqual([]));
  test("returns [] for malformed JSON", () => expect(parseDismissedHints("{not json")).toEqual([]));
  test("returns [] for a JSON object instead of an array", () =>
    expect(parseDismissedHints('{"chat":true}')).toEqual([]));
});
