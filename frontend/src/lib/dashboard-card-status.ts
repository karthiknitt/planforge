// Dashboard project-card status — pure status→UI mapping, kept separate from
// dashboard-strings.tsx (a "use client" component file) so it's
// unit-testable without rendering, same pattern as structural-status.ts.
//
// 4-state, widened from the original 3-state (approved / changes_requested /
// generic-awaiting) domain the card badge used before T23. A 5th
// "generating" state was considered — see task-23-report.md — but collapsed
// into "not_generated": no backend endpoint lists in-progress jobs, so
// there's no reliable per-tab-independent signal to distinguish them without
// a backend change, which is out of scope for this task.
export type CardStatus = "not_generated" | "awaiting" | "approved" | "changes_requested";

// `hasLayouts` comes from the backend's bulk `has_layouts` field (see
// app/(app)/dashboard/fetch-project-layout-map.ts); `approvalStatus` is the
// Drizzle/backend-shared `project.approval_status` column.
export function deriveCardStatus(hasLayouts: boolean, approvalStatus: string | null): CardStatus {
  if (!hasLayouts) return "not_generated";
  if (approvalStatus === "approved") return "approved";
  if (approvalStatus === "changes_requested") return "changes_requested";
  // Generated but no client response yet — covers both "not shared yet" and
  // "shared, no response yet" (approvalStatus stays null for both; the
  // backend never actually writes "pending", see share.py).
  return "awaiting";
}
