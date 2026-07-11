import { describe, expect, test } from "bun:test";
import { extractToolResults, isToolPart, toolPartLabel } from "./chat-parts";

describe("isToolPart", () => {
  test("is true for a static tool-<name> part", () => {
    expect(isToolPart({ type: "tool-move_room", toolCallId: "1", state: "input-available" })).toBe(
      true
    );
  });

  test("is true for a dynamic-tool part", () => {
    expect(
      isToolPart({
        type: "dynamic-tool",
        toolName: "refresh_layout",
        toolCallId: "1",
        state: "input-available",
      })
    ).toBe(true);
  });

  test("is false for text and reasoning parts", () => {
    expect(isToolPart({ type: "text", text: "hello" })).toBe(false);
    expect(isToolPart({ type: "reasoning", text: "thinking" })).toBe(false);
  });

  test("is false for malformed values without throwing", () => {
    expect(isToolPart(undefined)).toBe(false);
    expect(isToolPart(null)).toBe(false);
    expect(isToolPart(42)).toBe(false);
    expect(isToolPart("tool-move_room")).toBe(false);
    expect(isToolPart({})).toBe(false);
    expect(isToolPart({ type: 123 })).toBe(false);
  });
});

describe("toolPartLabel", () => {
  test("derives toolName from a static tool-<name> part's type", () => {
    expect(
      toolPartLabel({ type: "tool-move_room", toolCallId: "1", state: "input-streaming" })
    ).toEqual({ toolName: "move_room", state: "input-streaming" });
  });

  test("derives toolName from a dynamic-tool part's toolName field", () => {
    expect(
      toolPartLabel({
        type: "dynamic-tool",
        toolName: "refresh_layout",
        toolCallId: "1",
        state: "output-available",
      })
    ).toEqual({ toolName: "refresh_layout", state: "output-available" });
  });

  test("reports output-error state distinctly", () => {
    expect(
      toolPartLabel({
        type: "tool-add_room",
        toolCallId: "1",
        state: "output-error",
        errorText: "boom",
      })
    ).toEqual({ toolName: "add_room", state: "output-error" });
  });

  test("does not throw on malformed input", () => {
    expect(() => toolPartLabel(null)).not.toThrow();
    expect(() => toolPartLabel(undefined)).not.toThrow();
    expect(() => toolPartLabel("nonsense")).not.toThrow();
  });
});

describe("extractToolResults", () => {
  test("extracts a completed static tool-<name> part", () => {
    const parts = [
      {
        type: "tool-refresh_layout",
        toolCallId: "1",
        state: "output-available",
        input: {},
        output: { layout: { floors: [] } },
      },
    ];
    expect(extractToolResults(parts)).toEqual([
      { toolName: "refresh_layout", output: { layout: { floors: [] } } },
    ]);
  });

  test("extracts a completed dynamic-tool part via its toolName field", () => {
    const parts = [
      {
        type: "dynamic-tool",
        toolName: "move_room",
        toolCallId: "2",
        state: "output-available",
        input: { roomId: "r1" },
        output: { ok: true },
      },
    ];
    expect(extractToolResults(parts)).toEqual([{ toolName: "move_room", output: { ok: true } }]);
  });

  test("ignores tool parts still streaming or awaiting input", () => {
    const parts = [
      { type: "tool-move_room", toolCallId: "1", state: "input-streaming", input: {} },
      { type: "tool-move_room", toolCallId: "1", state: "input-available", input: {} },
      {
        type: "dynamic-tool",
        toolName: "resize_room",
        toolCallId: "2",
        state: "input-available",
        input: {},
      },
    ];
    expect(extractToolResults(parts)).toEqual([]);
  });

  test("excludes tool parts in an output-error state", () => {
    const parts = [
      {
        type: "tool-add_room",
        toolCallId: "1",
        state: "output-error",
        input: {},
        errorText: "Room not found",
      },
    ];
    expect(extractToolResults(parts)).toEqual([]);
  });

  test("ignores non-tool parts such as text and reasoning", () => {
    const parts = [
      { type: "text", text: "Sure, moving the room now." },
      { type: "reasoning", text: "The user wants..." },
      { type: "step-start" },
    ];
    expect(extractToolResults(parts)).toEqual([]);
  });

  test("handles a mix of tool and non-tool parts, preserving order", () => {
    const parts = [
      { type: "text", text: "Working on it..." },
      {
        type: "tool-move_room",
        toolCallId: "1",
        state: "output-available",
        input: {},
        output: { moved: true },
      },
      {
        type: "dynamic-tool",
        toolName: "refresh_layout",
        toolCallId: "2",
        state: "output-available",
        input: {},
        output: { layout: { floors: [] } },
      },
    ];
    expect(extractToolResults(parts)).toEqual([
      { toolName: "move_room", output: { moved: true } },
      { toolName: "refresh_layout", output: { layout: { floors: [] } } },
    ]);
  });

  test("does not throw on malformed part objects mixed into the array", () => {
    const parts: unknown[] = [
      null,
      undefined,
      42,
      "tool-move_room",
      {},
      { type: 123 },
      { type: "tool-move_room" },
    ];
    expect(() => extractToolResults(parts)).not.toThrow();
    expect(extractToolResults(parts)).toEqual([]);
  });

  test("returns an empty array for an empty parts list", () => {
    expect(extractToolResults([])).toEqual([]);
  });
});
