export const ALL_TABS = [
  "plan",
  "section",
  "compare",
  "chat",
  "structural",
  "boq",
  "r3f",
  "render",
] as const;
export type TabId = (typeof ALL_TABS)[number];

export function visibleTabs(): TabId[] {
  // Chat is always visible; the Pro-tier gate lives inside ChatTab itself
  // (a friendly "Pro plan required" upsell), so hiding the tab at this
  // layer would just duplicate that gate in a worse, less discoverable way.
  return [...ALL_TABS];
}
