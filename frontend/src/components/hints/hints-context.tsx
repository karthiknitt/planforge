"use client";

import { createContext, useCallback, useContext, useState } from "react";
import type { HintId } from "@/lib/hint-ids";

interface HintsContextValue {
  isDismissed: (id: HintId) => boolean;
  dismiss: (id: HintId) => void;
}

const HintsContext = createContext<HintsContextValue | null>(null);

// Wraps the project page's client tree so any tab trigger / toolbar button /
// panel toggle can check-or-dismiss its own first-visit hint without prop
// drilling through layout-viewer.tsx's already-large prop lists. Seeded from
// the server-read `user.dismissed_hints` column (see page.tsx), so a hint a
// user already dismissed on a previous visit never flashes on this one.
export function HintsProvider({
  initialDismissed,
  children,
}: {
  initialDismissed: HintId[];
  children: React.ReactNode;
}) {
  const [dismissed, setDismissed] = useState<Set<HintId>>(() => new Set(initialDismissed));

  const dismiss = useCallback((id: HintId) => {
    setDismissed((prev) => {
      if (prev.has(id)) return prev;
      const next = new Set(prev);
      next.add(id);
      return next;
    });
    // Fire-and-forget, same as onboarding-checklist.tsx's dismiss — worst
    // case on a failed write is the hint reappearing next visit, not a
    // blocked UI.
    fetch("/api/user/hints", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hintId: id }),
    }).catch(() => {});
  }, []);

  const isDismissed = useCallback((id: HintId) => dismissed.has(id), [dismissed]);

  return <HintsContext.Provider value={{ isDismissed, dismiss }}>{children}</HintsContext.Provider>;
}

export function useHints(): HintsContextValue {
  const ctx = useContext(HintsContext);
  if (!ctx) throw new Error("useHints must be used inside <HintsProvider>");
  return ctx;
}
