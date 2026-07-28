import arcjet, { detectBot, shield, tokenBucket } from "@arcjet/next";

const ARCJET_KEY = process.env.ARCJET_KEY ?? "";

// True once ARCJET_KEY is configured (only in Vercel's env store per this
// project's convention — there's no local .env value). Every call site skips
// protection when false so an unconfigured key never breaks a deploy.
export const arcjetEnabled = ARCJET_KEY.length > 0;

// Global attack-pattern (SQLi/XSS-style payload) detection. Runs once per
// request in proxy.ts before anything else, covering every matched route —
// pages and API alike, except /api/auth (Better Auth's own handler).
export const ajShield = arcjet({
  key: ARCJET_KEY,
  rules: [shield({ mode: "LIVE" })],
});

type RateLimitConfig = { refillRate: number; interval: string; capacity: number };

/**
 * Per-route client: a token-bucket budget keyed by userId. Shield already
 * runs globally in proxy.ts for this request, so it isn't repeated here —
 * only rate limiting is route-specific.
 */
export function rateLimitedClient(config: RateLimitConfig) {
  return arcjet({
    key: ARCJET_KEY,
    characteristics: ["userId"],
    rules: [tokenBucket({ mode: "LIVE", ...config })],
  });
}

/**
 * Same as above plus bot detection — for transcribe, the one route that
 * previously had no auth gate and is the highest-value target for blocking
 * non-browser clients outright.
 */
export function rateLimitedClientWithBotDetection(config: RateLimitConfig) {
  return arcjet({
    key: ARCJET_KEY,
    characteristics: ["userId"],
    rules: [tokenBucket({ mode: "LIVE", ...config }), detectBot({ mode: "LIVE", allow: [] })],
  });
}
