import { describe, expect, it } from "bun:test";
import { boqBasisLabel, hasBasisData, shouldShowPreliminaryBanner } from "./boq-provenance";

describe("boqBasisLabel", () => {
  it('labels "designed" as IS-code designed', () => {
    expect(boqBasisLabel("designed")).toBe("IS-code designed");
  });

  it('labels "estimated" and anything else (including missing) as estimated', () => {
    expect(boqBasisLabel("estimated")).toBe("estimated");
    expect(boqBasisLabel(null)).toBe("estimated");
    expect(boqBasisLabel(undefined)).toBe("estimated");
    expect(boqBasisLabel("unknown")).toBe("estimated");
  });
});

describe("hasBasisData", () => {
  it("is false when items are missing or none carry a basis", () => {
    expect(hasBasisData({})).toBe(false);
    expect(hasBasisData({ items: [] })).toBe(false);
    expect(hasBasisData({ items: [{}, {}] })).toBe(false);
  });

  it("is true once any item carries a basis", () => {
    expect(hasBasisData({ items: [{}, { basis: "estimated" }] })).toBe(true);
  });
});

describe("shouldShowPreliminaryBanner", () => {
  it("respects an explicit top-level preliminary flag", () => {
    expect(shouldShowPreliminaryBanner({ preliminary: true, items: [{ basis: "designed" }] })).toBe(
      true
    );
    expect(
      shouldShowPreliminaryBanner({ preliminary: false, items: [{ basis: "estimated" }] })
    ).toBe(false);
  });

  it("falls back to true (preliminary) when no basis data is present at all", () => {
    expect(shouldShowPreliminaryBanner({})).toBe(true);
    expect(shouldShowPreliminaryBanner({ items: [{}] })).toBe(true);
  });

  it("is false when basis data exists and no explicit flag overrides it", () => {
    expect(shouldShowPreliminaryBanner({ items: [{ basis: "designed" }] })).toBe(false);
  });
});
