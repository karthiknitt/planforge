export type CadQuality = {
  total: number;
  max: number;
  monochrome: number;
  dimension_density: number;
  ft_in_labels: number;
  layout_completeness: number;
};

export function cadQualityLabel(q: CadQuality): string {
  return `CAD ${Math.round(q.total)}/${q.max}`;
}

export function cadQualityTone(q: CadQuality): "good" | "ok" | "poor" {
  if (q.total >= 70) return "good";
  if (q.total >= 50) return "ok";
  return "poor";
}
