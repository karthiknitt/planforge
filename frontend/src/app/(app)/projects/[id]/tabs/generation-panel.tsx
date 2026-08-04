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
  const [cancelled, setCancelled] = useState(false);
  const startedRef = useRef(false);
  const pollCountRef = useRef(0);
  // Wall-clock start of the current job, used to derive elapsed time from
  // the poll loop's own re-renders (each poll tick calls setJob, which
  // re-renders this component) rather than running a second independent
  // setInterval just for a clock.
  const startedAtRef = useRef<number | null>(null);
  // The stop() fn startPolling() returns — stashed here so a user-facing
  // Cancel button can invoke it directly, not just the effect's unmount
  // cleanup.
  const stopPollRef = useRef<(() => void) | null>(null);

  const start = useCallback(async () => {
    setError("");
    setJob(null);
    setCancelled(false);
    pollCountRef.current = 0;
    startedAtRef.current = Date.now();
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
    if (!job || phase === "done" || phase === "failed" || cancelled) return;
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
    stopPollRef.current = stop;
    return () => {
      stop();
      stopPollRef.current = null;
    };
  }, [job?.id, phase, projectId, cancelled]);

  // Stops client-side polling only — it does NOT cancel the backend
  // generate-job. The CP-SAT solve keeps running server-side to completion
  // (or failure) regardless; this page simply stops asking about it. A
  // later "Start again" click POSTs a brand-new generate-job rather than
  // resuming the cancelled one, so the original job (if it later finishes)
  // is orphaned, not deleted or reused. True backend cancellation would
  // need a backend endpoint, which is out of scope for this task.
  const handleCancel = useCallback(() => {
    stopPollRef.current?.();
    stopPollRef.current = null;
    setCancelled(true);
  }, []);

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

  if (cancelled) {
    return (
      <output className="block rounded-lg border border-dashed p-10 text-center">
        <p className="font-medium">Generation cancelled</p>
        <p className="mt-1 text-sm text-muted-foreground">
          We stopped checking for a result. The job may still be finishing on the server, but this
          page won&apos;t wait for it.
        </p>
        <Button variant="outline" size="sm" className="mt-3" onClick={start}>
          Start again
        </Button>
      </output>
    );
  }

  // Elapsed time is derived from startedAtRef on every render this
  // component produces — every poll tick calls setJob(), which re-renders
  // this component, so the elapsed figure stays current without a second
  // independent timer.
  const elapsedS = startedAtRef.current
    ? Math.round((Date.now() - startedAtRef.current) / 1000)
    : 0;

  return (
    <output className="block rounded-lg border border-dashed p-10 text-center">
      <div
        aria-hidden="true"
        className="mx-auto h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent"
      />
      <p className="mt-3 font-medium">Generating your 3 layouts</p>
      <p className="mt-1 text-sm text-muted-foreground">
        {job ? stageLabel(job.stage) : "Starting…"}
        {startedAtRef.current ? ` · ${elapsedS}s elapsed` : ""}
      </p>
      {job && (
        <Button variant="ghost" size="sm" className="mt-3" onClick={handleCancel}>
          Cancel
        </Button>
      )}
    </output>
  );
}
