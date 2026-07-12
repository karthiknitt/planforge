import { describe, expect, test } from "bun:test";
import { visibleTabs } from "./tabs";

describe("visibleTabs", () => {
  test("chat hidden by default", () => expect(visibleTabs(false)).not.toContain("chat"));
  test("chat shown when enabled", () => expect(visibleTabs(true)).toContain("chat"));
  test("other tabs always present", () =>
    expect(visibleTabs(false)).toEqual([
      "plan",
      "section",
      "boq",
      "structural",
      "compare",
      "r3f",
      "render",
    ]));
});
