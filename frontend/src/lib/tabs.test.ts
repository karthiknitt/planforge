import { describe, expect, test } from "bun:test";
import { visibleTabs } from "./tabs";

describe("visibleTabs", () => {
  test("chat always present", () => expect(visibleTabs()).toContain("chat"));
  test("all tabs present in order", () =>
    expect(visibleTabs()).toEqual([
      "plan",
      "section",
      "boq",
      "structural",
      "r3f",
      "render",
      "compare",
      "chat",
    ]));
});
