export const TYPE_LABELS: Record<string, string> = {
  living: "Living / Hall",
  bedroom: "Bedroom",
  master_bedroom: "Master Bedroom",
  kitchen: "Kitchen",
  toilet: "Toilet",
  staircase: "Staircase",
  parking: "Parking",
  utility: "Utility / Other",
  pooja: "Pooja Room",
  study: "Study",
  balcony: "Balcony",
  dining: "Dining",
  servant_quarter: "Servant Quarter",
  home_office: "Home Office",
  gym: "Gym",
  store_room: "Store Room",
  garage: "Garage",
  passage: "Passage",
  foyer: "Foyer",
  courtyard: "Courtyard",
  wardrobe: "Wardrobe",
};

// Light values are the original palette. Dark variants are hue-matched to
// floor-plan-svg.tsx's PALETTE_DARK for the same room type (same fill/stroke
// family, just expressed as Tailwind classes instead of raw hex) so the
// legend swatches read as visually related to the SVG room fills in dark
// mode, and stay legible against the near-black dark background.
export const SWATCH: Record<string, string> = {
  living: "bg-yellow-100 border-yellow-400 dark:bg-yellow-950/40 dark:border-yellow-500",
  bedroom: "bg-violet-100 border-violet-500 dark:bg-violet-950/40 dark:border-violet-500",
  master_bedroom: "bg-purple-100 border-purple-500 dark:bg-purple-950/40 dark:border-purple-500",
  kitchen: "bg-green-100 border-green-600 dark:bg-green-950/40 dark:border-green-500",
  toilet: "bg-sky-100 border-sky-500 dark:bg-sky-950/40 dark:border-sky-500",
  staircase: "bg-slate-100 border-slate-400 dark:bg-slate-800/50 dark:border-slate-500",
  parking: "bg-slate-50 border-slate-300 dark:bg-slate-800/40 dark:border-slate-500",
  utility: "bg-slate-50 border-slate-300 dark:bg-slate-800/40 dark:border-slate-500",
  pooja: "bg-orange-50 border-orange-400 dark:bg-orange-950/40 dark:border-orange-500",
  study: "bg-emerald-50 border-emerald-500 dark:bg-emerald-950/40 dark:border-emerald-500",
  balcony: "bg-blue-50 border-blue-400 dark:bg-sky-950/40 dark:border-sky-500",
  dining: "bg-yellow-50 border-yellow-500 dark:bg-yellow-950/40 dark:border-yellow-500",
  servant_quarter: "bg-orange-50 border-orange-500 dark:bg-orange-950/40 dark:border-orange-500",
  home_office: "bg-green-50 border-green-500 dark:bg-green-950/40 dark:border-green-500",
  gym: "bg-red-50 border-red-400 dark:bg-rose-950/40 dark:border-rose-500",
  store_room: "bg-slate-50 border-slate-400 dark:bg-slate-800/40 dark:border-slate-500",
  garage: "bg-blue-50 border-blue-500 dark:bg-sky-950/40 dark:border-sky-500",
  passage: "bg-slate-100 border-slate-400 dark:bg-slate-800/50 dark:border-slate-500",
  foyer: "bg-slate-100 border-slate-400 dark:bg-slate-800/50 dark:border-slate-500",
  courtyard: "bg-blue-50 border-blue-400 dark:bg-sky-950/40 dark:border-sky-500",
  wardrobe: "bg-slate-50 border-slate-400 dark:bg-slate-800/40 dark:border-slate-500",
};
