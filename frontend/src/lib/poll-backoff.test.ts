import { describe, expect, it } from "bun:test";
import { backoffDelayMs, startPolling } from "./poll-backoff";

describe("backoffDelayMs", () => {
  it("uses the first tier's delay before any polls have run", () => {
    expect(backoffDelayMs(0)).toBe(2000);
    expect(backoffDelayMs(4)).toBe(2000);
  });

  it("steps up to the second tier once the threshold is reached", () => {
    expect(backoffDelayMs(5)).toBe(5000);
    expect(backoffDelayMs(9)).toBe(5000);
  });

  it("caps at the final tier and never regresses", () => {
    expect(backoffDelayMs(10)).toBe(10_000);
    expect(backoffDelayMs(1000)).toBe(10_000);
  });

  it("supports custom tiers", () => {
    const tiers = [
      { afterPolls: 0, delayMs: 100 },
      { afterPolls: 2, delayMs: 300 },
    ];
    expect(backoffDelayMs(0, tiers)).toBe(100);
    expect(backoffDelayMs(2, tiers)).toBe(300);
  });
});

// Small tiers so the suite runs fast; real timers (no fake-timer dependency).
const fastTiers = [{ afterPolls: 0, delayMs: 5 }];

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

describe("startPolling", () => {
  it("ticks repeatedly until stopped", async () => {
    let ticks = 0;
    const stop = startPolling({
      pollCountRef: { current: 0 },
      maxPolls: 1000,
      tiers: fastTiers,
      isHidden: () => false,
      tick: async () => {
        ticks += 1;
      },
      onTimeout: () => {
        throw new Error("should not time out");
      },
    });
    await wait(30);
    stop();
    const ticksAtStop = ticks;
    expect(ticksAtStop).toBeGreaterThan(1);
    await wait(20);
    // No further ticks after stop() — the chain must not keep rescheduling.
    expect(ticks).toBe(ticksAtStop);
  });

  it("never overlaps a slow tick with the next one", async () => {
    let inFlight = 0;
    let overlapped = false;
    const stop = startPolling({
      pollCountRef: { current: 0 },
      maxPolls: 1000,
      tiers: fastTiers,
      isHidden: () => false,
      tick: async () => {
        if (inFlight > 0) overlapped = true;
        inFlight += 1;
        await wait(15);
        inFlight -= 1;
      },
      onTimeout: () => {},
    });
    await wait(50);
    stop();
    expect(overlapped).toBe(false);
  });

  it("skips fetching (and counting) while the tab is hidden, and resumes once visible", async () => {
    let hidden = true;
    let ticks = 0;
    const pollCountRef = { current: 0 };
    const stop = startPolling({
      pollCountRef,
      maxPolls: 1000,
      tiers: fastTiers,
      isHidden: () => hidden,
      tick: async () => {
        ticks += 1;
      },
      onTimeout: () => {},
    });
    await wait(25);
    expect(ticks).toBe(0);
    expect(pollCountRef.current).toBe(0);
    hidden = false;
    await wait(30);
    stop();
    expect(ticks).toBeGreaterThan(0);
  });

  it("calls onTimeout and stops once pollCount exceeds maxPolls", async () => {
    let timedOut = false;
    let ticks = 0;
    startPolling({
      pollCountRef: { current: 0 },
      maxPolls: 2,
      tiers: fastTiers,
      isHidden: () => false,
      tick: async () => {
        ticks += 1;
      },
      onTimeout: () => {
        timedOut = true;
      },
    });
    await wait(60);
    expect(timedOut).toBe(true);
    const ticksAtTimeout = ticks;
    expect(ticksAtTimeout).toBe(2);
    await wait(30);
    // onTimeout does not itself schedule another tick.
    expect(ticks).toBe(ticksAtTimeout);
  });
});
