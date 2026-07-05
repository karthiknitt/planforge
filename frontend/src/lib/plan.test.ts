import { describe, expect, test } from "bun:test";
import { tierAtLeast } from "./plan";

describe("tierAtLeast", () => {
  test("firm >= pro", () => expect(tierAtLeast("firm", "pro")).toBe(true));
  test("basic < pro", () => expect(tierAtLeast("basic", "pro")).toBe(false));
  test("null tier ranks as free", () => expect(tierAtLeast(null, "basic")).toBe(false));
  test("unknown tier ranks as free", () => expect(tierAtLeast("x", "basic")).toBe(false));
});
