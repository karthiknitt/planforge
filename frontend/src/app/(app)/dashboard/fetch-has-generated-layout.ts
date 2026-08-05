import { fetchBackend } from "@/lib/backend-fetch";

type ProjectWithLayoutFlag = { has_layouts?: boolean };

// Onboarding-checklist step 2 ("generate/review") needs to know whether *any*
// of the user's projects has a stored, generated layout — a fact that only
// exists in the backend's `layouts` table, not in the Drizzle-fetched
// project rows this page otherwise renders from. This is a non-critical
// progress hint, not core dashboard functionality, so a slow or unreachable
// backend (e.g. a Cloud Run cold start) must never block or fail the
// dashboard render — timeout short and fall back to `false` (treated as
// "not yet confirmed done") on any error.
export async function fetchHasGeneratedLayout(userId: string): Promise<boolean> {
  try {
    const res = await fetchBackend(userId, "projects", { timeoutMs: 4000 });
    if (!res.ok) {
      return false;
    }
    const projects: ProjectWithLayoutFlag[] = await res.json();
    return projects.some((p) => p.has_layouts === true);
  } catch {
    return false;
  }
}
