/**
 * Shared scheduling core for the render-job and generation-job polls in
 * layout-viewer.tsx. A self-rescheduling setTimeout chain (not setInterval)
 * so overlapping fetches are structurally impossible — the next tick is only
 * scheduled after the current one settles — and the delay can grow between
 * ticks (exponential-ish backoff) without a clearInterval/setInterval dance.
 */

import { POLL_INTERVAL_MS } from "./generation-job";

export interface BackoffTier {
  /** Delay applies once pollCount (already-completed polls) reaches this. */
  afterPolls: number;
  delayMs: number;
}

/** 2s for the first 5 polls, 5s for the next 5, 10s for the rest. */
export const DEFAULT_BACKOFF_TIERS: readonly BackoffTier[] = [
  { afterPolls: 0, delayMs: POLL_INTERVAL_MS },
  { afterPolls: 5, delayMs: 5000 },
  { afterPolls: 10, delayMs: 10_000 },
];

export function backoffDelayMs(
  pollCount: number,
  tiers: readonly BackoffTier[] = DEFAULT_BACKOFF_TIERS
): number {
  let delay = tiers[0].delayMs;
  for (const tier of tiers) {
    if (pollCount >= tier.afterPolls) delay = tier.delayMs;
  }
  return delay;
}

export interface PollOptions {
  /** Shared with the caller so it can be reset (e.g. when a new job starts). */
  pollCountRef: { current: number };
  maxPolls: number;
  /** Performs one poll (fetch + state update); must be safe to call at most once at a time. */
  tick: () => Promise<void>;
  onTimeout: () => void;
  /** Injectable for tests; defaults to the page's visibility state. */
  isHidden?: () => boolean;
  tiers?: readonly BackoffTier[];
}

const defaultIsHidden = () => typeof document !== "undefined" && document.hidden;

/**
 * Starts a backoff-aware poll loop. Returns a stop function (call from a
 * useEffect cleanup). A tick that's still hidden-skipped or in flight never
 * overlaps the next one, since re-scheduling only happens after the previous
 * tick (or hidden-skip) has fully resolved.
 */
export function startPolling({
  pollCountRef,
  maxPolls,
  tick,
  onTimeout,
  isHidden = defaultIsHidden,
  tiers = DEFAULT_BACKOFF_TIERS,
}: PollOptions): () => void {
  let stopped = false;
  let timeoutId: ReturnType<typeof setTimeout> | undefined;

  const schedule = () => {
    if (stopped) return;
    timeoutId = setTimeout(runTick, backoffDelayMs(pollCountRef.current, tiers));
  };

  async function runTick() {
    if (stopped) return;
    if (isHidden()) {
      // Tab isn't visible — skip this tick's fetch, don't count it, try again later.
      schedule();
      return;
    }
    pollCountRef.current += 1;
    if (pollCountRef.current > maxPolls) {
      onTimeout();
      return;
    }
    try {
      await tick();
    } finally {
      if (!stopped) schedule();
    }
  }

  schedule();
  return () => {
    stopped = true;
    if (timeoutId !== undefined) clearTimeout(timeoutId);
  };
}
