"use client";

import { AlertTriangle, CheckCircle2, Circle, Info } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { needsApproval, type StatusTone, statusBadgeInfo } from "@/lib/structural-status";

export const TONE_CLASS: Record<StatusTone, string> = {
  muted: "border-border bg-muted text-muted-foreground",
  info: "border-info/40 bg-info/10 text-info",
  success: "border-success/40 bg-success/10 text-success",
  warning: "border-warning/40 bg-warning/10 text-warning",
};

const TONE_ICON: Record<StatusTone, typeof Circle> = {
  muted: Circle,
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
};

interface StructuralLifecycleHeaderProps {
  status: string | null | undefined;
  changelog: string[];
  approving: boolean;
  onApprove: () => Promise<void> | void;
  onRunDesign: () => void;
}

export function StructuralLifecycleHeader({
  status,
  changelog,
  approving,
  onApprove,
  onRunDesign,
}: StructuralLifecycleHeaderProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [changelogOpen, setChangelogOpen] = useState(false);
  const badge = statusBadgeInfo(status);
  const Icon = TONE_ICON[badge.tone];
  const showApprove = needsApproval(status);
  const showRunDesign = status === "approved";
  const showChangelog = status === "designed" || status === "designed_with_warnings";

  async function handleConfirmApprove() {
    await onApprove();
    setConfirmOpen(false);
  }

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-muted/20 px-3 py-2">
      <Badge
        variant="outline"
        className={`gap-1 border ${TONE_CLASS[badge.tone]}`}
        aria-label={`Structural status: ${badge.label}`}
      >
        <Icon className="h-3 w-3" aria-hidden="true" />
        {badge.label}
      </Badge>

      {showApprove && (
        <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <DialogTrigger asChild>
            <Button size="sm" variant="outline">
              Approve plan
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Approve this architectural plan?</DialogTitle>
              <DialogDescription>
                Approving freezes this plan&apos;s current geometry as the baseline for structural
                design. Architectural drawings remain preliminary — for planning only, not for
                construction — until a structural design has been run against this approved
                revision. Any further edit to the layout automatically reverts it back to draft.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConfirmOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleConfirmApprove} disabled={approving}>
                {approving ? "Approving…" : "Approve"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {showRunDesign && (
        <Button size="sm" variant="outline" onClick={onRunDesign}>
          Run structural design
        </Button>
      )}

      {showChangelog && (
        <Dialog open={changelogOpen} onOpenChange={setChangelogOpen}>
          <DialogTrigger asChild>
            <Button size="sm" variant="ghost" className="gap-1 text-xs">
              View changes ({changelog.length})
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Changes from the approved plan</DialogTitle>
              <DialogDescription>
                {changelog.length === 0
                  ? "No adjustments were required — the approved architectural grid satisfied structural checks as-is."
                  : "The structural design loop adjusted the following to satisfy IS-code checks:"}
              </DialogDescription>
            </DialogHeader>
            {changelog.length > 0 && (
              <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                {changelog.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            )}
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
