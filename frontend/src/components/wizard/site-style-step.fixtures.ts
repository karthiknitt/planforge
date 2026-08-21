/**
 * Fixture mirroring GET /api/backend/style-presets' payload shape
 * (`asdict(StylePreset)` from backend/app/api/routes/style_presets.py).
 * Only the styles the tests touch need real prevalence numbers; they are
 * copied verbatim from backend/app/engine/style_presets.py.
 */
export interface PresetPayload {
  median_plot_sqft: number;
  typical_bhk: string;
  prevalence: Record<string, number>;
}

export const PRESETS_FIXTURE: Record<string, PresetPayload> = {
  Kerala: {
    median_plot_sqft: 2091,
    typical_bhk: "4 BHK",
    prevalence: {
      courtyard: 30,
      verandah: 10,
      car_porch_open: 50,
      terrace: 30,
      pooja: 10,
      study: 0,
    },
  },
  Goan: {
    median_plot_sqft: 2385,
    typical_bhk: "4 BHK",
    prevalence: {
      courtyard: 33,
      verandah: 8,
      car_porch_open: 58,
      terrace: 16,
      pooja: 16,
      study: 0,
    },
  },
};
