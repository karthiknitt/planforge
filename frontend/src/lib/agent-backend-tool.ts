import { z } from "zod";
import { type FetchBackendInit, fetchBackend } from "@/lib/backend-fetch";

// Agent tool calls can stack a CP-SAT-free read on top of a Cloud Run cold
// start (~23s measured), so the default 15s fetch budget is too tight — the
// route allows a long maxDuration, give each backend call 45s.
export const AGENT_TOOL_TIMEOUT_MS = 45_000;

export const NO_LAYOUTS_TOOL_RESULT =
  "No layouts exist yet — ask the user to generate layouts first from the project page.";

// Model-controlled room identifiers are interpolated into backend URL paths, so
// constrain them to an opaque-id shape (no slashes, dots, or whitespace) to
// block path traversal at the schema layer. Executors also encodeURIComponent.
export const roomIdSchema = z.string().regex(/^[A-Za-z0-9_-]+$/, "invalid room id");

// Deterministic opening ids (plan_geometry.assign_opening_ids) look like
// "w:v:i:a>b@4.44:7.67-13.88#0.622" — they legitimately contain ':' '#' '.'
// '>' and '@', so the schema is wider than roomIdSchema's. Slashes are still
// banned, and executors still encodeURIComponent before the id hits the URL
// (a raw '#' would otherwise terminate the path as a fragment).
export const openingIdSchema = z.string().regex(/^[A-Za-z0-9_:.,#>@+-]+$/, "invalid opening id");

type FetchBackendFn = (userId: string, path: string, init?: FetchBackendInit) => Promise<Response>;

// Shared wrapper for every agent tool: applies the 45s timeout and turns the
// backend's 409 {code: no_layouts} into a conversational result the model can
// relay, rather than a thrown error that surfaces as an error banner.
//
// `fetchImpl` is injectable for testing; production callers use the default.
export async function callBackendTool(
  userId: string,
  path: string,
  init?: RequestInit,
  fetchImpl: FetchBackendFn = fetchBackend
): Promise<unknown> {
  const res = await fetchImpl(userId, path, {
    ...init,
    timeoutMs: AGENT_TOOL_TIMEOUT_MS,
  });
  if (res.status === 409) {
    const body = (await res.json().catch(() => null)) as {
      detail?: { code?: string };
    } | null;
    if (body?.detail?.code === "no_layouts") {
      return NO_LAYOUTS_TOOL_RESULT;
    }
    return body ?? { error: "Request conflicts with the current layout state" };
  }
  // A non-JSON body on a non-409 response lets res.json() throw. That is
  // intentional: ai@6's executeToolCall catches a thrown tool execute and
  // emits a `tool-error` part the model can recover from, so it never crashes
  // the assistant stream.
  return res.json();
}
