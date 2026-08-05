export const ALL_TABS = [
  "plan",
  "section",
  "boq",
  "structural",
  "r3f",
  "render",
  "compare",
  "chat",
] as const;
export type TabId = (typeof ALL_TABS)[number];

export function visibleTabs(): TabId[] {
  // Chat is always visible; the Pro-tier gate lives inside ChatTab itself
  // (a friendly "Pro plan required" upsell), so hiding the tab at this
  // layer would just duplicate that gate in a worse, less discoverable way.
  return [...ALL_TABS];
}
