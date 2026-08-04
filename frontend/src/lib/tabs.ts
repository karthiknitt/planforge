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

export function visibleTabs(agentChatEnabled: boolean): TabId[] {
  return ALL_TABS.filter((t) => t !== "chat" || agentChatEnabled);
}
