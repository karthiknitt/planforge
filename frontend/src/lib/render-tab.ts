export function buildRenderImageUrl(projectId: string, layoutKey: string, version: number): string {
  return `/api/backend/projects/${encodeURIComponent(projectId)}/layouts/${encodeURIComponent(layoutKey)}/render?v=${version}`;
}

export type RenderStatusOutcome = "ready" | "upsell" | "unavailable" | "error";

export function classifyRenderStatus(status: number): RenderStatusOutcome {
  if (status >= 200 && status < 300) return "ready";
  if (status === 402) return "upsell";
  if (status === 503) return "unavailable";
  return "error";
}
