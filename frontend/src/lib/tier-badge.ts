export const TIER_BADGE: Record<string, { label: string; className: string }> = {
  free: {
    label: "Free",
    className: "bg-muted/80 text-muted-foreground border border-border/60",
  },
  basic: {
    label: "Basic",
    className: "bg-blue-500/10 text-blue-400 border border-blue-500/20",
  },
  pro: {
    label: "Pro",
    className: "bg-primary/10 text-primary border border-primary/25",
  },
  firm: {
    label: "Firm",
    className: "bg-purple-500/10 text-purple-400 border border-purple-500/20",
  },
};
