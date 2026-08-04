"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

// Surfaced once the initial solve is clearly running long — a manual escape
// hatch for a stuck/slow request. Not a hard timeout: fetchLayouts() (server
// side, see fetch-layouts.ts) has its own backend timeout/retry behaviour;
// this is purely a client-facing "reload and try again" affordance.
const RETRY_AFTER_S = 20;

// ── Generating fallback (shown while the solver runs) ───────────────────────
// This is a Server Component's Suspense fallback (see page.tsx), rendered
// while LayoutSection awaits fetchLayouts() on the server during the
// project's initial solve. At this point in the request lifecycle there is
// no client-side job object to poll — fetchLayouts() is a single direct
// backend GET, not a job-status poll loop like GenerationPanel/RenderTab use
// — so this component cannot show genuine solver-stage transitions ("Solving
// layout constraints" → "Scoring layouts" → …) without inventing them. What
// it CAN show honestly is real elapsed wall-clock time (ticked client-side
// from the moment this fallback mounts) plus an indeterminate progress
// indicator that doesn't claim to know a percentage or stage. A true cancel
// isn't feasible at this layer either — there's no in-flight fetch/job on
// the client to abort, only a server-side await; reloading the page (which
// re-runs the whole request) is the closest honest equivalent, offered here
// as "Retry" once the wait is clearly abnormal.
export function GeneratingFallback() {
  const [elapsedS, setElapsedS] = useState(0);

  useEffect(() => {
    const startedAt = Date.now();
    const id = setInterval(() => {
      setElapsedS(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="flex flex-col gap-6 rounded-2xl border border-dashed border-border bg-muted/20 px-8 py-10">
      {/* Progress bar — output element gives this an implicit status role,
          matching the ARIA pattern already used in generation-panel.tsx. */}
      <output className="flex flex-col gap-2">
        <div className="flex items-center justify-between text-sm">
          <span className="font-medium text-foreground">Generating floor plans…</span>
          <span className="text-xs text-muted-foreground tabular-nums">{elapsedS}s elapsed</span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
          {/* No real progress percentage is known here — an animated but
              non-claiming fill, not a fake "almost done" value. */}
          <div className="h-full w-2/5 animate-pulse rounded-full bg-primary" />
        </div>
        <p className="text-xs text-muted-foreground">
          The solver is generating and scoring layout options against your plot and compliance
          rules. This usually takes a few seconds.
        </p>
      </output>

      {elapsedS >= RETRY_AFTER_S && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-sm">
          <span className="text-muted-foreground">
            This is taking longer than usual — you can reload to try again.
          </span>
          <Button variant="outline" size="sm" onClick={() => window.location.reload()}>
            Retry
          </Button>
        </div>
      )}

      {/* Skeleton cards for layout buttons — h-11 (44px) matches the real
          "Layout {id} — {name}" buttons' min-h-[44px] in layout-viewer.tsx */}
      <div className="flex gap-3 pt-2">
        {["w-28", "w-36", "w-32"].map((w) => (
          <Skeleton key={w} className={`h-11 ${w} rounded-lg`} />
        ))}
      </div>

      {/* SVG area skeleton — width matches FloorPlanSVG's "w-full md:max-w-xl" */}
      <Skeleton className="h-72 w-full rounded-xl bg-muted/60 md:max-w-xl" />
    </div>
  );
}
