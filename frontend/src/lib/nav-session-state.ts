export type NavSessionState = "pending" | "authenticated" | "anonymous";

interface SessionQuery {
  isPending?: boolean;
  data?: unknown;
  error?: unknown;
}

/**
 * Marketing nav renders a neutral placeholder until the client-side session
 * resolves, so a wrong CTA never flashes before hydration settles.
 */
export function navSessionState({ isPending, data, error }: SessionQuery): NavSessionState {
  if (isPending) return "pending";
  if (error) return "anonymous";
  return data ? "authenticated" : "anonymous";
}
