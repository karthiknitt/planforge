import { describe, expect, test } from "bun:test";
import en from "../../messages/en.json";
import { isLocale, loadMessages } from "./locale-context";

describe("isLocale", () => {
  test("accepts the three known locales", () => {
    expect(isLocale("en")).toBe(true);
    expect(isLocale("ta")).toBe(true);
    expect(isLocale("hi")).toBe(true);
  });

  test("rejects unknown or missing values", () => {
    expect(isLocale("fr")).toBe(false);
    expect(isLocale("")).toBe(false);
    expect(isLocale(undefined)).toBe(false);
  });
});

describe("loadMessages", () => {
  test("resolves 'en' immediately from the eagerly-bundled dictionary", async () => {
    const messages = await loadMessages("en");
    expect(messages).toBe(en);
  });

  test("lazily loads 'ta' and returns a dictionary shaped like the fallback", async () => {
    const messages = await loadMessages("ta");
    expect(Object.keys(messages).sort()).toEqual(Object.keys(en).sort());
    expect(typeof messages.rooms).toBe("object");
  });

  test("lazily loads 'hi' and returns a dictionary shaped like the fallback", async () => {
    const messages = await loadMessages("hi");
    expect(Object.keys(messages).sort()).toEqual(Object.keys(en).sort());
    expect(typeof messages.rooms).toBe("object");
  });

  test("caches the resolved dictionary — repeated calls return the same object", async () => {
    const first = await loadMessages("ta");
    const second = await loadMessages("ta");
    expect(second).toBe(first);
  });

  test("dedupes concurrent in-flight loads for the same locale", async () => {
    // Two calls fired before either resolves must share one underlying
    // import — this is what stops a rapid double-click on the language
    // toggle from kicking off two separate dynamic imports.
    const [a, b] = await Promise.all([loadMessages("hi"), loadMessages("hi")]);
    expect(a).toBe(b);
  });
});
