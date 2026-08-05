import type { useSession } from "@/lib/auth-client";

export type NavSessionState = "pending" | "authenticated" | "anonymous";

/**
 * Pinned to Better Auth's own hook return type: a field renamed upstream becomes
 * a build error here instead of silently resolving every user to "anonymous".
 */
export type SessionQuery = Pick<ReturnType<typeof useSession>, "isPending" | "data" | "error">;

/**
 * Marketing nav renders a neutral placeholder until the client-side session
 * resolves, so a wrong CTA never flashes before hydration settles.
 */
export function navSessionState({ isPending, data, error }: SessionQuery): NavSessionState {
  if (isPending) return "pending";
  if (error) return "anonymous";
  return data ? "authenticated" : "anonymous";
}
