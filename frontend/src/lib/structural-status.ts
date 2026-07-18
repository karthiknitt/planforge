// Stage 2 structural lifecycle — pure status→UI mapping, kept separate from
// the components so it's unit-testable without rendering. Lifecycle is
// DERIVED server-side (see backend/app/services/structural_store.py):
//   draft:    no ArchitecturalRevision matches the current geometry hash
//   approved: a matching revision exists, no live design on it
//   designed / designed_with_warnings: from the latest non-stale design row
// "stale" is filtered out by the backend's `latest_design` query and never
// returned on the `status` field, but we map it defensively anyway in case
// that ever changes (e.g. a future endpoint surfaces raw design rows).

export type StructuralLifecycleStatus =
  | "draft"
  | "approved"
  | "designed"
  | "designed_with_warnings"
  | "stale";

export type StatusTone = "muted" | "info" | "success" | "warning";

export interface StatusBadgeInfo {
  label: string;
  tone: StatusTone;
}

export function statusBadgeInfo(status: string | null | undefined): StatusBadgeInfo {
  switch (status) {
    case "approved":
      return { label: "APPROVED", tone: "info" };
    case "designed":
      return { label: "DESIGNED · IS-code", tone: "success" };
    case "designed_with_warnings":
      return { label: "DESIGNED · with warnings", tone: "warning" };
    case "stale":
      return { label: "STALE · re-run design", tone: "warning" };
    default:
      return { label: "DRAFT · preliminary", tone: "muted" };
  }
}

// Gates the "Approve plan" action — only a draft (no matching revision yet)
// needs it. `null`/`undefined` (status not loaded yet, or no rows at all)
// is treated as draft since that's the backend's own default.
export function needsApproval(status: string | null | undefined): boolean {
  return status !== "approved" && status !== "designed" && status !== "designed_with_warnings";
}

// Drives the "PRELIMINARY — for planning only" notice on architectural
// views: shown until a live (non-stale) design exists, warnings or not.
export function isPreliminaryStatus(status: string | null | undefined): boolean {
  return status !== "designed" && status !== "designed_with_warnings";
}

export function changelogCount(changelog: readonly string[] | null | undefined): number {
  return changelog?.length ?? 0;
}

// Render-source toggle (R3F / AI render conditioning) — GET
// .../structural/design returns 409 (code not_approved) when the layout
// hasn't been approved yet, 404 (code not_designed) when it's approved but
// no design exists, or 200 with final_geometry: null when the structural
// loop needed no geometry adjustment. All fall back to the architectural
// geometry, but with a different explanation.
export type RenderSourceFallbackReason = "no_design" | "no_adjustment" | "not_approved";

export function renderSourceFallbackNote(reason: RenderSourceFallbackReason): string {
  if (reason === "no_adjustment") {
    return "Structural design made no geometry changes — showing the architectural view.";
  }
  if (reason === "not_approved") {
    return "Plan not approved yet — approve the architectural plan first.";
  }
  return "No structural design yet for this layout — showing the architectural view.";
}
