"use client";

import type { project } from "@/db/schema";
import { ProjectCard } from "./dashboard-strings";

type Project = typeof project.$inferSelect;

// Client island wrapping the project-card grid — a "use client" boundary
// mirrors the pattern T22 established for GeneratingFallback (server-fetched
// initial data as props, client-side behavior from there). Currently just
// renders; approval-status polling is layered on in a follow-up commit.
export function DashboardProjectGrid({
  projects,
  hasLayoutsMap,
  variant,
}: {
  projects: Project[];
  hasLayoutsMap: Record<string, boolean>;
  variant: "own" | "team";
}) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {projects.map((p, i) => (
        <ProjectCard
          key={p.id}
          project={p}
          variant={variant}
          animationDelayMs={100 + i * 60}
          hasLayouts={hasLayoutsMap[p.id] ?? false}
        />
      ))}
    </div>
  );
}
