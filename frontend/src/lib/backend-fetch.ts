import { signInternalAuthToken } from "@/lib/internal-auth";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

const DEFAULT_TIMEOUT_MS = 15_000;

// Extends RequestInit with an optional per-call timeout. Callers that hit a
// path known to be slow (e.g. the agent tool endpoints stacked on a Cloud Run
// cold start) can raise it above the 15s default.
//
// `email` (optional, non-breaking) carries the caller's verified session
// email into the internal auth token's `email` claim — used by backend
// endpoints (e.g. team-invite claim) that must trust an email but never
// accept one from a request body.
export type FetchBackendInit = RequestInit & { timeoutMs?: number; email?: string };

export async function fetchBackend(
  userId: string,
  path: string,
  init?: FetchBackendInit
): Promise<Response> {
  const secret = process.env.INTERNAL_AUTH_SECRET;
  if (!secret) {
    throw new Error("INTERNAL_AUTH_SECRET is not set");
  }
  const token = await signInternalAuthToken(userId, secret, init?.email);
  // Normalize via Headers() first — init.headers may legitimately be a plain
  // object, a Headers instance, or a [string, string][] tuple array, and
  // object-spreading only handles the first of those correctly.
  const headers = new Headers(init?.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("X-Internal-Auth", token);

  const { timeoutMs, email: _email, ...requestInit } = init ?? {};
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs ?? DEFAULT_TIMEOUT_MS);
  // Combine the caller's signal (if any) with the timeout signal so BOTH can
  // abort the request — previously a caller-supplied signal silently discarded
  // the timeout, leaving slow-backend calls able to hang past timeoutMs.
  const signal = init?.signal
    ? AbortSignal.any([init.signal, controller.signal])
    : controller.signal;
  try {
    return await fetch(`${BACKEND_URL}/api/${path.replace(/^\//, "")}`, {
      ...requestInit,
      headers,
      signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }
}
