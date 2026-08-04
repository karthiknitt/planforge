import { fetchBackend } from "@/lib/backend-fetch";

type ProjectWithLayoutFlag = { id?: string; has_layouts?: boolean };

// Sibling to fetch-has-generated-layout.ts (T20's onboarding-checklist
// helper, which collapses the whole project list down to a single "does ANY
// project have layouts" boolean — not reusable as-is for a per-card status
// chip). This hits the same bulk, non-N+1 `GET /projects` endpoint
// (backend/app/api/routes/projects.py's list_projects, one indexed
// `SELECT DISTINCT project_id FROM layouts WHERE project_id IN (...)` query
// added in T20) but returns the raw per-project map instead.
//
// A card's "Generating" state was considered and rejected for this task —
// see dashboard-strings.tsx's CardStatus comment — so `has_layouts` is only
// ever used to distinguish "not generated" from "generated", nothing finer.
//
// Non-critical progress data, same failure posture as
// fetch-has-generated-layout.ts: a slow/unreachable backend (e.g. a Cloud
// Run cold start) must never block or fail the dashboard render, so this
// times out short and falls back to an empty map (every card reads as "not
// generated" until a later load succeeds) rather than throwing.
export async function fetchProjectLayoutMap(userId: string): Promise<Record<string, boolean>> {
  try {
    const res = await fetchBackend(userId, "projects", { timeoutMs: 4000 });
    if (!res.ok) {
      return {};
    }
    const projects: ProjectWithLayoutFlag[] = await res.json();
    const map: Record<string, boolean> = {};
    for (const p of projects) {
      if (p.id) map[p.id] = p.has_layouts === true;
    }
    return map;
  } catch {
    return {};
  }
}
