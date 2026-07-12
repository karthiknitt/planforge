export type RenderFloorKey = "ground_floor" | "first_floor" | "second_floor" | "basement_floor";

export function floorKeyFromIndex(index: number): RenderFloorKey {
  if (index === -1) return "basement_floor";
  if (index === 1) return "first_floor";
  if (index === 2) return "second_floor";
  return "ground_floor";
}

export function buildRenderImageUrl(
  projectId: string,
  layoutKey: string,
  version: number,
  floor: RenderFloorKey = "ground_floor"
): string {
  return `/api/backend/projects/${encodeURIComponent(projectId)}/layouts/${encodeURIComponent(layoutKey)}/render?floor=${floor}&v=${version}`;
}

export type RenderStatusOutcome = "ready" | "upsell" | "unavailable" | "error";

export function classifyRenderStatus(status: number): RenderStatusOutcome {
  if (status >= 200 && status < 300) return "ready";
  if (status === 402) return "upsell";
  if (status === 503) return "unavailable";
  return "error";
}
