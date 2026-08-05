// Pure predicate for bounding approval-status polling — shared by the
// dashboard's client-island poller (dashboard-project-grid.tsx) and (in a
// follow-up commit) the project page's own poll loop. Kept separate so the
// "what counts as genuinely awaiting a response" rule is unit-testable
// without rendering, and can't silently drift between the two call sites.
//
// A project is only "genuinely awaiting a response" once it has actually
// been shared (shareToken set — see backend/app/api/routes/share.py's
// POST /projects/{id}/share) AND the client hasn't responded yet
// (approvalStatus still null). This is deliberately narrower than the
// dashboard card's "awaiting" status bucket (lib/dashboard-card-status.ts),
// which also covers "generated but never shared" — polling a project nobody
// has been asked to review yet would never resolve and would just poll
// forever for no reason.
export function isAwaitingApprovalResponse(
  shareToken: string | null | undefined,
  approvalStatus: string | null
): boolean {
  return !!shareToken && approvalStatus === null;
}

// Same order of magnitude as generation-job.ts's MAX_POLLS (36, ≈5 min
// wall-clock via poll-backoff's tiered delays) — approval status is a
// slower-moving, lower-urgency signal (a human client responding, not a
// solver job), so a shorter ceiling is fine.
export const APPROVAL_POLL_MAX_POLLS = 18;
