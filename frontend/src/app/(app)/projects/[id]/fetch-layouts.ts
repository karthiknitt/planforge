import { unstable_cache } from "next/cache";
import { fetchBackend } from "@/lib/backend-fetch";
import type { GenerateResponse } from "@/lib/layout-types";

// fetchBackend() mints a fresh short-lived signed token on every call, which
// would otherwise be part of Next's fetch cache key and defeat caching on
// every request (the token never repeats). unstable_cache() caches on
// projectId alone — the token minting only happens on an actual cache miss.
// Project access is team-widened (owner OR team member), so the cache key
// includes userId — a projectId-only key could serve one user's cached
// entry to another authorised user, and would become a cross-user leak if
// authorisation rules ever drift again.
//
// The loader THROWS on any failure (non-OK or network error): unstable_cache
// stores fulfilled values but never rejections, so a transient Cloud Run
// rollover/cold-start failure is not negative-cached for 5 minutes — the
// next request retries. The catch sits outside the cached wrapper; null
// means "backend unreachable right now", while "no layouts yet" is a
// successful response with an empty layouts list.
export async function fetchLayouts(
  projectId: string,
  userId: string
): Promise<GenerateResponse | null> {
  const getCached = unstable_cache(
    async (): Promise<GenerateResponse> => {
      const res = await fetchBackend(userId, `projects/${projectId}/layouts`);
      if (!res.ok) {
        throw new Error(`layouts fetch failed with status ${res.status}`);
      }
      return res.json();
    },
    [`project-generate-${projectId}`, userId],
    { revalidate: 300, tags: [`project-${projectId}`] }
  );
  try {
    return await getCached();
  } catch {
    return null;
  }
}
