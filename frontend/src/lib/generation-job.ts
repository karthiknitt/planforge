export type JobPhase = "idle" | "queued" | "running" | "done" | "failed";

export interface JobStatus {
  id: string;
  status: string;
  stage: string;
  error: string | null;
}

export const POLL_INTERVAL_MS = 2000;
export const MAX_POLLS = 150; // 5 minutes — past this, surface a timeout error

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
