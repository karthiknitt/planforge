// First-visit discoverability hints (P2.7). Each id is one independently
// dismissible "have you seen this?" popover. Persisted server-side as a JSON
// array in user.dismissed_hints (see db/schema.ts) — this module owns the
// shape of that array so the API route and the server-rendered page agree
// on what a valid entry looks like.
export const HINT_IDS = ["chat", "overlays", "compare", "history"] as const;
export type HintId = (typeof HINT_IDS)[number];

export function isHintId(value: unknown): value is HintId {
  return typeof value === "string" && (HINT_IDS as readonly string[]).includes(value);
}

// Tolerant parse: a missing column default, malformed JSON, or a stray
// non-array/non-string value all just mean "nothing dismissed yet" rather
// than a thrown error surfacing on the project page.
export function parseDismissedHints(raw: string | null | undefined): HintId[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isHintId);
  } catch {
    return [];
  }
}
