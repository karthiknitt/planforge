"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { type JobStatus, jobPhase, MAX_POLLS, stageLabel } from "@/lib/generation-job";
import { startPolling } from "@/lib/poll-backoff";
import { showErrorToast } from "@/lib/toast";

// ── Generation panel — polls a generate-job to completion, then refreshes ──
export function GenerationPanel({
  projectId,
  autoStart,
  onDone,
}: {
  projectId: string;
  autoStart: boolean;
  onDone?: () => void;
}) {
  const router = useRouter();
  const [job, setJob] = useState<JobStatus | null>(null);
  const [error, setError] = useState("");
  const startedRef = useRef(false);
  const pollCountRef = useRef(0);

  const start = useCallback(async () => {
    setError("");
    setJob(null);
    pollCountRef.current = 0;
    try {
      const res = await fetch(`/api/backend/projects/${projectId}/generate-jobs`, {
        method: "POST",
      });
      if (!res.ok) {
        const message = `Could not start generation (HTTP ${res.status}).`;
        setError(message);
        showErrorToast(message);
        return;
      }
      setJob(await res.json());
    } catch {
      setError("Could not reach the layout engine.");
      showErrorToast("Could not reach the layout engine.");
    }
  }, [projectId]);

  useEffect(() => {
    if (autoStart && !startedRef.current) {
      startedRef.current = true;
      start();
    }
  }, [autoStart, start]);

  const phase = jobPhase(job);

  // biome-ignore lint/correctness/useExhaustiveDependencies: keyed on job?.id deliberately, not the full job object — every poll tick replaces job with a new reference, and depending on it would tear down/recreate the poll loop on every tick
  useEffect(() => {
    if (!job || phase === "done" || phase === "failed") return;
    const stop = startPolling({
      pollCountRef,
      maxPolls: MAX_POLLS,
      tick: async () => {
        try {
          const res = await fetch(`/api/backend/projects/${projectId}/jobs/${job.id}`);
          if (res.ok) setJob(await res.json());
        } catch {
          /* transient poll failure — keep polling */
        }
      },
      onTimeout: () => {
        setError("Generation is taking unusually long — try refreshing the page.");
        showErrorToast("Generation is taking unusually long — try refreshing the page.");
      },
    });
    return stop;
  }, [job?.id, phase, projectId]);

  useEffect(() => {
    if (phase !== "done") return;
    fetch(`/api/projects/${projectId}/revalidate`, { method: "POST" }).finally(() => {
      onDone?.();
      router.refresh();
    });
  }, [phase, projectId, router, onDone]);

  if (error || phase === "failed") {
    return (
      <div role="alert" className="rounded-lg border border-destructive/40 p-6 text-center">
        <p className="text-sm text-destructive">{error || job?.error || "Generation failed."}</p>
        <Button variant="outline" size="sm" className="mt-3" onClick={start}>
          Try again
        </Button>
      </div>
    );
  }
  return (
    <output className="block rounded-lg border border-dashed p-10 text-center">
      <div
        aria-hidden="true"
        className="mx-auto h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent"
      />
      <p className="mt-3 font-medium">Generating your 3 layouts</p>
      <p className="mt-1 text-sm text-muted-foreground">
        {job ? stageLabel(job.stage) : "Starting…"}
      </p>
    </output>
  );
}
