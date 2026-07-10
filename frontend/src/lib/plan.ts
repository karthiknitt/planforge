export const TIER_ORDER = ["free", "basic", "pro", "firm"] as const;

function rank(tier: string | null | undefined): number {
  const i = TIER_ORDER.indexOf((tier ?? "free") as (typeof TIER_ORDER)[number]);
  return i === -1 ? 0 : i;
}

export function tierAtLeast(tier: string | null | undefined, minimum: string): boolean {
  return rank(tier) >= rank(minimum);
}
