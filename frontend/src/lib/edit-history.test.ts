import { describe, expect, test } from "bun:test";
import {
  canRedo,
  canUndo,
  initHistory,
  pushHistory,
  redoHistory,
  undoHistory,
} from "./edit-history";

describe("edit-history", () => {
  test("init has no undo/redo", () => {
    const h = initHistory([1]);
    expect(canUndo(h)).toBe(false);
    expect(canRedo(h)).toBe(false);
  });
  test("push then undo restores previous", () => {
    let h = initHistory([1]);
    h = pushHistory(h, [2]);
    expect(canUndo(h)).toBe(true);
    h = undoHistory(h);
    expect(h.present).toEqual([1]);
    expect(canRedo(h)).toBe(true);
  });
  test("redo replays the undone state", () => {
    let h = pushHistory(initHistory([1]), [2]);
    h = redoHistory(undoHistory(h));
    expect(h.present).toEqual([2]);
  });
  test("push clears the redo stack", () => {
    let h = pushHistory(initHistory([1]), [2]);
    h = undoHistory(h);
    h = pushHistory(h, [3]);
    expect(canRedo(h)).toBe(false);
  });
  test("history is capped at 50 entries", () => {
    let h = initHistory(0 as unknown as number[]);
    for (let i = 1; i <= 60; i++) h = pushHistory(h, i as unknown as number[]);
    expect(h.past.length).toBe(50);
  });
  test("undo/redo at the boundary are no-ops", () => {
    const h = initHistory([1]);
    expect(undoHistory(h)).toBe(h);
    expect(redoHistory(h)).toBe(h);
  });
});
