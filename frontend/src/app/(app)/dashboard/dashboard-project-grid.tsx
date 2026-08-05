"use client";

import { useEffect, useRef, useState } from "react";
import type { project } from "@/db/schema";
import { APPROVAL_POLL_MAX_POLLS, isAwaitingApprovalResponse } from "@/lib/approval-poll";
import { startPolling } from "@/lib/poll-backoff";
import { ProjectCard } from "./dashboard-strings";

type Project = typeof project.$inferSelect;

interface ApprovalSnapshot {
  approvalStatus: string | null;
  approvalNote: string | null;
}

// Client island wrapping the project-card grid, polling approval status for
// "own" projects — mirrors the pattern T22 established for
// GeneratingFallback: server-fetched initial data as props, then client-side
// polling from there via the shared lib/poll-backoff.ts engine (same
// contract as generation-panel.tsx / render-tab.tsx — a pollCountRef, a
// tick() fn, an onTimeout, a stop() cleanup).
//
// Approach chosen over a new Drizzle-backed route handler (the task's other
// option): frontend/src/CLAUDE.md's ownership rule reserves Drizzle for auth
// tables and treats the rest (including `project`) as backend-owned
// Postgres, reached through `/api/` routes or backend-fetch.ts. The project
// page's existing fetchApprovalStatus() already hits
// GET /api/backend/projects/{id}/approval-status per project — reusing that
// endpoint here keeps a single source of truth for "how the frontend reads
// approval status" instead of adding a second (Drizzle) read path for the
// same data. It's also bounded by construction (see isAwaitingApprovalResponse
// in lib/approval-poll.ts): only projects that were actually shared and
// haven't been responded to yet are ever polled, and the whole loop stops
// itself the moment none remain.
export function DashboardProjectGrid({
  projects,
  hasLayoutsMap,
  variant,
}: {
  projects: Project[];
  hasLayoutsMap: Record<string, boolean>;
  variant: "own" | "team";
}) {
  const [statuses, setStatuses] = useState<Record<string, ApprovalSnapshot>>(() =>
    Object.fromEntries(
      projects.map((p) => [
        p.id,
        { approvalStatus: p.approvalStatus, approvalNote: p.approvalNote },
      ])
    )
  );
  // Refs mirror the latest state/props for the poll tick's closure — the
  // effect below intentionally mounts once per `variant` (see the lint
  // suppression on it), so it must never read stale state/props captured at
  // mount time.
  const statusesRef = useRef(statuses);
  statusesRef.current = statuses;
  const shareTokenByIdRef = useRef(new Map(projects.map((p) => [p.id, p.shareToken])));
  shareTokenByIdRef.current = new Map(projects.map((p) => [p.id, p.shareToken]));
  const pollCountRef = useRef(0);
  const stopRef = useRef<(() => void) | null>(null);

  // biome-ignore lint/correctness/useExhaustiveDependencies: intentionally mount-once per `variant` — the pollable set is re-derived from statusesRef/shareTokenByIdRef each tick (always current), not from a dependency that would tear down and restart the loop on every parent re-render
  useEffect(() => {
    if (variant !== "own") return;
    const anyPollable = projects.some((p) =>
      isAwaitingApprovalResponse(p.shareToken, statusesRef.current[p.id]?.approvalStatus ?? null)
    );
    if (!anyPollable) return;

    const stop = startPolling({
      pollCountRef,
      maxPolls: APPROVAL_POLL_MAX_POLLS,
      tick: async () => {
        const pollableIds = Object.keys(statusesRef.current).filter((id) =>
          isAwaitingApprovalResponse(
            shareTokenByIdRef.current.get(id) ?? null,
            statusesRef.current[id]?.approvalStatus ?? null
          )
        );
        if (pollableIds.length === 0) {
          stopRef.current?.();
          return;
        }
        const results = await Promise.all(
          pollableIds.map(async (id) => {
            try {
              const res = await fetch(`/api/backend/projects/${id}/approval-status`);
              if (!res.ok) return null;
              const data = await res.json();
              return {
                id,
                approvalStatus: (data.approval_status ?? null) as string | null,
                approvalNote: (data.approval_note ?? null) as string | null,
              };
            } catch {
              // Transient poll failure for this project — silent, matches
              // the project page's own fetchApprovalStatus() convention
              // (approval status is non-critical). Keep polling; a stuck
              // backend eventually hits onTimeout below.
              return null;
            }
          })
        );
        setStatuses((prev) => {
          let changed = false;
          const next = { ...prev };
          for (const r of results) {
            if (r && r.approvalStatus !== prev[r.id]?.approvalStatus) {
              next[r.id] = { approvalStatus: r.approvalStatus, approvalNote: r.approvalNote };
              changed = true;
            }
          }
          return changed ? next : prev;
        });
      },
      onTimeout: () => {
        // Silent — this is a background dashboard refresh, not a
        // user-initiated action; nagging with a toast for a non-critical
        // status check would be noisy. The project page's manual "↻" button
        // (and its own polling) still works once the user opens it.
      },
    });
    stopRef.current = stop;
    return () => {
      stop();
      stopRef.current = null;
    };
  }, [variant]);

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {projects.map((p, i) => (
        <ProjectCard
          key={p.id}
          project={p}
          variant={variant}
          animationDelayMs={100 + i * 60}
          hasLayouts={hasLayoutsMap[p.id] ?? false}
          approvalStatus={statuses[p.id]?.approvalStatus ?? null}
          approvalNote={statuses[p.id]?.approvalNote ?? null}
        />
      ))}
    </div>
  );
}
