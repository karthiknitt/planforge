import { describe, expect, it } from "bun:test";
import { type CadQuality, cadQualityLabel, cadQualityTone } from "./cad-quality";

const q = (total: number): CadQuality => ({
  total,
  max: 80,
  monochrome: 20,
  dimension_density: 20,
  ft_in_labels: 20,
  layout_completeness: 20,
});

describe("cadQualityLabel", () => {
  it("formats as CAD n/80 with rounding", () => {
    expect(cadQualityLabel(q(76.4))).toBe("CAD 76/80");
    expect(cadQualityLabel(q(80))).toBe("CAD 80/80");
  });
});

describe("cadQualityTone", () => {
  it("classifies good/ok/poor at 70 and 50 thresholds", () => {
    expect(cadQualityTone(q(72))).toBe("good");
    expect(cadQualityTone(q(60))).toBe("ok");
    expect(cadQualityTone(q(40))).toBe("poor");
  });
});
