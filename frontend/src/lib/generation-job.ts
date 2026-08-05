export type JobPhase = "idle" | "queued" | "running" | "done" | "failed";

export interface JobStatus {
  id: string;
  status: string;
  stage: string;
  error: string | null;
}

export const POLL_INTERVAL_MS = 2000;
// Poll-count cap, not a fixed wall-clock window: poll-backoff.ts's DEFAULT_BACKOFF_TIERS
// grow the interval over time (2s for polls 0-4, 5s for polls 5-9, 10s from poll 10 on),
// so this must be sized to keep the *wall-clock* timeout ceiling close to the original
// flat-2s-interval ~5 minutes (2000 * 150), not just kept at the old poll count.
// sum_{i=0}^{35} tier(i) = 5*2000 + 5*5000 + 26*10000 = 295_000ms ≈ 4.92 min.
export const MAX_POLLS = 36;

export function jobPhase(job: JobStatus | null): JobPhase {
  if (!job) return "idle";
  switch (job.status) {
    case "queued":
      return "queued";
    case "done":
      return "done";
    case "failed":
      return "failed";
    default:
      return "running";
  }
}

const STAGE_LABELS: Record<string, string> = {
  queued: "Queued…",
  solving: "Solving layouts…",
  rendering: "Rendering…",
  stored: "Finalizing…",
};

export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? "Working…";
}
