import { describe, expect, test } from "bun:test";
import en from "../../../messages/en.json";
import { loadInitialMessages } from "./layout";

describe("loadInitialMessages", () => {
  test("returns undefined for 'en' — LocaleProvider already has it statically bundled", async () => {
    const messages = await loadInitialMessages("en");
    expect(messages).toBeUndefined();
  });

  test("resolves the real 'ta' dictionary at request time (not English)", async () => {
    const messages = await loadInitialMessages("ta");
    expect(messages).toBeDefined();
    expect(Object.keys(messages ?? {}).sort()).toEqual(Object.keys(en).sort());
    // Spot-check the resolved dictionary is actually Tamil, not the English
    // fallback — this is exactly the bug the SSR-seeding fix addresses.
    expect(messages?.nav).not.toEqual(en.nav);
  });

  test("resolves the real 'hi' dictionary at request time (not English)", async () => {
    const messages = await loadInitialMessages("hi");
    expect(messages).toBeDefined();
    expect(Object.keys(messages ?? {}).sort()).toEqual(Object.keys(en).sort());
    expect(messages?.nav).not.toEqual(en.nav);
  });
});
