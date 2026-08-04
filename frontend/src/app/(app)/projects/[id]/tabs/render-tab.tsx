"use client";

import { Lock, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { type JobStatus, jobPhase, MAX_POLLS, stageLabel } from "@/lib/generation-job";
import { tierAtLeast } from "@/lib/plan";
import { startPolling } from "@/lib/poll-backoff";
import {
  buildRenderImageUrl,
  classifyRenderStatus,
  floorKeyFromIndex,
  type RenderFloorKey,
} from "@/lib/render-tab";
import { showErrorToast } from "@/lib/toast";

// ── Render tab — generate + view AI renders per floor, Pro-gated ──────────────
// One FloorRenderSection per available floor: "checking" probes the GET
// endpoint (via a hidden <img>) to see if a render already exists; "busy"
// tracks an in-flight POST separately so a regenerate can keep showing the
// last successful image.
type RenderPhase = "checking" | "none" | "ready" | "upsell" | "unavailable" | "error";

export function RenderTab({
  projectId,
  layoutKey,
  planTier,
  floors,
  r3fPngs,
  registerTrigger,
  capturing,
}: {
  projectId: string;
  layoutKey: string;
  planTier: string;
  floors: { label: string; index: number }[];
  r3fPngs: Record<number, string | null>;
  registerTrigger?: (fn: (floorIndex: number, png?: string | null) => void) => void;
  /** True while layout-viewer.tsx is capturing a fresh 3D-view PNG — see r3f-tab.tsx for the primary UI. */
  capturing?: boolean;
}) {
  const isPro = tierAtLeast(planTier, "pro");
  const sectionTriggers = useRef<Record<string, (png?: string | null) => void>>({});
  useEffect(() => {
    registerTrigger?.((floorIndex: number, png?: string | null) => {
      sectionTriggers.current[floorKeyFromIndex(floorIndex)]?.(png);
    });
  }, [registerTrigger]);

  if (!isPro) {
    return (
      <div className="rounded-xl border border-dashed border-amber-500/40 bg-amber-500/5 p-8 text-center">
        <Lock className="mx-auto mb-3 h-6 w-6 text-amber-600" />
        <p className="font-semibold text-amber-700 dark:text-amber-400">Pro plan required</p>
        <p className="mt-1 text-sm text-muted-foreground">AI renders are a Pro feature.</p>
        <Button asChild className="mt-4" size="sm" variant="outline">
          <Link href="/pricing">Upgrade to Pro</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <p className="text-sm text-muted-foreground">
        Visit the 3D View tab first — its geometric capture conditions each floor&apos;s
        photorealistic render. Generating without it still works, just from the plan alone.
      </p>
      {capturing && (
        <p className="text-xs text-muted-foreground">
          Capturing the 3D view for reference — generating now will pick it up once ready.
        </p>
      )}
      {floors.map((f) => (
        <FloorRenderSection
          key={f.index}
          projectId={projectId}
          layoutKey={layoutKey}
          floorKey={floorKeyFromIndex(f.index)}
          label={f.label}
          r3fPng={r3fPngs[f.index]}
          register={(fn) => {
            sectionTriggers.current[floorKeyFromIndex(f.index)] = fn;
          }}
        />
      ))}
    </div>
  );
}

function FloorRenderSection({
  projectId,
  layoutKey,
  floorKey,
  label,
  r3fPng,
  register,
}: {
  projectId: string;
  layoutKey: string;
  floorKey: RenderFloorKey;
  label: string;
  r3fPng?: string | null;
  register?: (fn: (png?: string | null) => void) => void;
}) {
  const [phase, setPhase] = useState<RenderPhase>("checking");
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);
  const [error, setError] = useState("");
  const [job, setJob] = useState<JobStatus | null>(null);
  const pollCountRef = useRef(0);
  // Always-current layout key, so an in-flight poll dispatched for the
  // previously-viewed layout can detect it resolved late (after a layout
  // switch) and drop its stale setJob instead of flipping phase to "ready".
  const layoutKeyRef = useRef(layoutKey);
  layoutKeyRef.current = layoutKey;

  // Latest generate fn, so the parent's trigger always calls the current closure.
  const handleGenRef = useRef<(png?: string | null) => void>(() => {});
  handleGenRef.current = (png?: string | null) => {
    void handleGenerate(png);
  };
  useEffect(() => {
    register?.((png?: string | null) => handleGenRef.current(png));
  }, [register]);

  // Reset and re-check whenever the viewed project/layout changes — the
  // version cache-buster must reset too, or a previous project's cached
  // image URL could be shown (the stale-render bug).
  // biome-ignore lint/correctness/useExhaustiveDependencies: projectId/layoutKey are intentional re-check triggers, not read in the body
  useEffect(() => {
    setPhase("checking");
    setError("");
    setJob(null);
    setVersion(0);
  }, [projectId, layoutKey]);

  async function handleGenerate(overridePng?: string | null) {
    setBusy(true);
    setError("");
    setJob(null);
    pollCountRef.current = 0;
    try {
      const fd = new FormData();
      const png = overridePng !== undefined ? overridePng : r3fPng;
      if (png) {
        const blob = await (await fetch(png)).blob();
        fd.append("reference", blob, "r3f.png");
      }
      const res = await fetch(
        `/api/backend/projects/${projectId}/layouts/${layoutKey}/render-jobs?floor=${floorKey}`,
        { method: "POST", body: fd }
      );
      const outcome = classifyRenderStatus(res.status);
      if (outcome === "upsell") {
        setPhase("upsell");
        setBusy(false);
        return;
      }
      if (outcome === "unavailable") {
        setPhase("unavailable");
        setBusy(false);
        return;
      }
      if (outcome !== "ready") {
        const data = await res.json().catch(() => ({}));
        const message = (data as { detail?: string })?.detail ?? `Render failed (${res.status})`;
        setError(message);
        setPhase("error");
        setBusy(false);
        showErrorToast(message);
        return;
      }
      // 200 (inline fallback, already resolved) or 202 (queued) — either way
      // the job-status poll below drives phase from here; busy stays true
      // until the job resolves.
      setJob(await res.json());
    } catch {
      setError("Render failed — is the backend running?");
      setPhase("error");
      setBusy(false);
      showErrorToast("Render failed — is the backend running?");
    }
  }

  const renderJobPhase = jobPhase(job);

  // biome-ignore lint/correctness/useExhaustiveDependencies: keyed on job?.id deliberately, not the full job object — every poll tick replaces job with a new reference, and depending on it would tear down/recreate the poll loop on every tick (layoutKey is a legitimate re-arm trigger and stays in the deps)
  useEffect(() => {
    if (!job || renderJobPhase === "done" || renderJobPhase === "failed") return;
    // This poll belongs to the layout viewed when it was armed; if the user
    // switches layouts, a late-resolving fetch must not setJob for the wrong one.
    const dispatchKey = layoutKey;
    const stop = startPolling({
      pollCountRef,
      maxPolls: MAX_POLLS,
      tick: async () => {
        try {
          const res = await fetch(`/api/backend/projects/${projectId}/jobs/${job.id}`);
          // Ignore a response that resolved after a layout switch.
          if (layoutKeyRef.current !== dispatchKey) return;
          if (res.ok) setJob(await res.json());
        } catch {
          /* transient poll failure — keep polling */
        }
      },
      onTimeout: () => {
        setError("Render is taking unusually long — try again.");
        setPhase("error");
        setBusy(false);
        showErrorToast("Render is taking unusually long — try again.");
      },
    });
    return stop;
  }, [job?.id, renderJobPhase, projectId, layoutKey]);

  useEffect(() => {
    if (renderJobPhase === "done") {
      setVersion((v) => v + 1);
      setPhase("ready");
      setBusy(false);
    } else if (renderJobPhase === "failed") {
      const message = job?.error ?? "Render failed.";
      setError(message);
      setPhase("error");
      setBusy(false);
      showErrorToast(message);
    }
  }, [renderJobPhase, job?.error]);

  return (
    <div className="flex flex-col gap-3">
      <p className="font-medium text-sm">{label}</p>
      {phase === "checking" && (
        <>
          {/* 8:5 matches the render service's fixed 1280x800 output (backend/app/services/render_providers.py) — keeps the skeleton box the same size as the loaded image. */}
          <Skeleton className="aspect-[8/5] h-auto w-full max-w-xl rounded-xl" />
          {/* Invisible probe: an existing render loads silently; a missing one (404) flips to "none". */}
          {/* biome-ignore lint/performance/noImgElement: proxied backend PNG of unknown dimensions, not a next/image candidate */}
          <img
            src={buildRenderImageUrl(projectId, layoutKey, version, floorKey)}
            alt=""
            className="hidden"
            onLoad={() => setPhase("ready")}
            onError={() => setPhase("none")}
          />
        </>
      )}

      {phase === "ready" && (
        <>
          {/* biome-ignore lint/performance/noImgElement: proxied backend PNG of unknown dimensions, not a next/image candidate */}
          <img
            src={buildRenderImageUrl(projectId, layoutKey, version, floorKey)}
            alt={`AI render — ${label}`}
            className="aspect-[8/5] w-full max-w-xl rounded-xl border object-cover"
          />
          {/* Regenerate in flight — the image above is deliberately still the
              last successful render (see FloorRenderSection's top comment),
              not hidden behind a skeleton; this line is the only signal that
              a new one is on the way. */}
          {busy && (
            <p className="text-xs text-muted-foreground">
              {job ? stageLabel(job.stage) : "Starting…"} — showing the previous render until this
              one finishes.
            </p>
          )}
        </>
      )}

      {busy && phase !== "ready" && (
        <>
          {/* 8:5 matches the render service's fixed 1280x800 output — same
              rationale as the "checking" skeleton above. Shown here (instead
              of an empty state) because there's no previous image to keep
              displaying while this floor's first/retry render is in flight. */}
          <Skeleton className="aspect-[8/5] h-auto w-full max-w-xl rounded-xl" />
          <p className="text-xs text-muted-foreground">
            {job ? stageLabel(job.stage) : "Starting…"}
          </p>
        </>
      )}

      {phase === "none" && !busy && (
        <p className="text-sm text-muted-foreground">
          No render yet for the {label.toLowerCase()} of this layout. Generate an AI-rendered
          visualisation from the current floor plan.
        </p>
      )}

      {phase === "unavailable" && (
        <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground">
          <p className="font-medium">Rendering isn't configured on this server yet.</p>
        </div>
      )}

      {phase === "upsell" && (
        <div className="rounded-xl border border-dashed border-amber-500/40 bg-amber-500/5 p-8 text-center">
          <Lock className="mx-auto mb-3 h-6 w-6 text-amber-600" />
          <p className="font-semibold text-amber-700 dark:text-amber-400">Pro plan required</p>
          <p className="mt-1 text-sm text-muted-foreground">AI renders are a Pro feature.</p>
          <Button asChild className="mt-4" size="sm" variant="outline">
            <Link href="/pricing">Upgrade to Pro</Link>
          </Button>
        </div>
      )}

      {error && (
        <p
          role="alert"
          className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
        >
          {error}
        </p>
      )}

      {(phase === "none" || phase === "ready" || phase === "error") && (
        <Button
          size="sm"
          variant={phase === "ready" ? "outline" : "default"}
          className="w-fit gap-1.5"
          onClick={() => void handleGenerate()}
          disabled={busy}
        >
          <RefreshCw className="h-3 w-3" />
          {busy
            ? job
              ? stageLabel(job.stage)
              : "Starting…"
            : phase === "ready"
              ? "Regenerate"
              : phase === "error"
                ? "Retry"
                : "Generate render"}
        </Button>
      )}
    </div>
  );
}
