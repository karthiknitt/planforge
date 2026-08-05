"use client";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { HintId } from "@/lib/hint-ids";
import { useHints } from "./hints-context";

// Wraps a single trigger element (a tab, a toolbar button, a panel toggle)
// in a popover that's open automatically the first time this user sees it,
// and stays open (there's no onOpenChange, so outside clicks/Escape don't
// silently dismiss it — mirrors share-whatsapp-button.tsx's
// `open={condition ? true : undefined}` pattern) until they explicitly
// dismiss it. After that it never opens for this user again — persisted via
// useHints()/dismiss(), not just this render.
export function FirstVisitHint({
  id,
  title,
  body,
  dismissLabel,
  side = "bottom",
  waitFor,
  children,
}: {
  id: HintId;
  title: string;
  body: string;
  dismissLabel: string;
  side?: "top" | "bottom" | "left" | "right";
  // Another hint's id this one queues behind — stays closed until that one
  // is dismissed, so two first-visit popovers never pop open at once and
  // overlap on screen.
  waitFor?: HintId;
  children: React.ReactNode;
}) {
  const { isDismissed, dismiss } = useHints();

  if (isDismissed(id)) {
    return children;
  }

  const open = waitFor ? isDismissed(waitFor) : true;

  return (
    <Popover open={open}>
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent side={side} className="w-64">
        <p className="font-medium text-sm">{title}</p>
        <p className="mt-1 text-xs text-muted-foreground">{body}</p>
        <button
          type="button"
          onClick={() => dismiss(id)}
          className="mt-3 w-full rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted transition-colors"
        >
          {dismissLabel}
        </button>
      </PopoverContent>
    </Popover>
  );
}
