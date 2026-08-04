"use client";

import { Check, ChevronDown, X } from "lucide-react";
import { useState } from "react";
import { StructuralLifecycleHeader } from "@/components/structural-lifecycle-header";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { ComplianceData, LayoutScoreData } from "@/lib/layout-types";
import { statusBadgeInfo } from "@/lib/structural-status";

// ── Vastu badge with popover for details ──────────────────────────────────────
function VastuBadge({ compliance }: { compliance: ComplianceData }) {
  const vastuViolations = compliance.violations.filter((v) => v.startsWith("[Vastu]"));
  const vastuWarnings = compliance.warnings.filter((w) => w.startsWith("[Vastu]"));
  const allIssues = [...vastuViolations, ...vastuWarnings];

  let badgeClass: string;
  let label: string;
  if (vastuViolations.length > 0) {
    badgeClass =
      "border-red-500/50 bg-red-500/10 text-red-700 dark:text-red-400 hover:bg-red-500/15";
    label = `${vastuViolations.length} Vastu Violation${vastuViolations.length !== 1 ? "s" : ""}`;
  } else if (vastuWarnings.length > 0) {
    badgeClass =
      "border-amber-500/50 bg-amber-500/10 text-amber-700 dark:text-amber-400 hover:bg-amber-500/15";
    label = `${vastuWarnings.length} Vastu Warning${vastuWarnings.length !== 1 ? "s" : ""}`;
  } else {
    badgeClass =
      "border-green-500/50 bg-green-500/10 text-green-700 dark:text-green-400 hover:bg-green-500/15";
    label = "Vastu Compliant";
  }

  if (allIssues.length === 0) {
    return (
      <span
        className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold ${badgeClass}`}
      >
        {label}
      </span>
    );
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold transition-colors cursor-pointer ${badgeClass}`}
        >
          {label}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80 text-sm" align="start">
        <p className="font-semibold mb-2 text-foreground">Vastu Issues</p>
        {vastuViolations.length > 0 && (
          <div className="mb-2">
            <p className="text-xs font-medium text-red-600 dark:text-red-400 mb-1">Violations</p>
            <ul className="space-y-1">
              {vastuViolations.map((v) => (
                <li key={v} className="text-xs text-muted-foreground">
                  {v.replace("[Vastu] ", "")}
                </li>
              ))}
            </ul>
          </div>
        )}
        {vastuWarnings.length > 0 && (
          <div>
            <p className="text-xs font-medium text-amber-600 dark:text-amber-400 mb-1">Warnings</p>
            <ul className="space-y-1">
              {vastuWarnings.map((w) => (
                <li key={w} className="text-xs text-muted-foreground">
                  {w.replace("[Vastu] ", "")}
                </li>
              ))}
            </ul>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}

const SCORE_FIELDS: {
  key: keyof Omit<LayoutScoreData, "total">;
  label: string;
  tip: string;
}[] = [
  {
    key: "natural_light",
    label: "Natural Light",
    tip: "Share of habitable rooms (living, bedrooms, kitchen, dining, study, office, gym, servant quarter) with an outer wall for windows and daylight.",
  },
  {
    key: "adjacency",
    label: "Room Adjacency",
    tip: "How well rooms that should share a wall actually do — e.g. kitchen next to dining, bedroom next to toilet, living room next to the staircase.",
  },
  {
    key: "aspect_ratio",
    label: "Aspect Ratio",
    tip: "Penalises long, sliver-shaped rooms — habitable rooms whose long side is more than twice their short side lose points.",
  },
  {
    key: "circulation",
    label: "Circulation / Fill",
    tip: "How efficiently the buildable area is used — scores best when 75-90% of the plot is filled by rooms, penalising both under- and over-filled layouts.",
  },
  {
    key: "vastu",
    label: "Vastu",
    tip: "Vastu Shastra zone and placement compliance — deducts points per violation and warning. Neutral 100 when Vastu checking isn't enabled.",
  },
];

interface StatusRailProps {
  score: LayoutScoreData | null;
  vastuEnabled: boolean;
  compliance: ComplianceData;
  municipality?: string | null;
  structStatus: string | null | undefined;
  structChangelog: string[];
  approvingStructural: boolean;
  onApproveStructural: () => Promise<void> | void;
  onRunStructuralDesign: () => void;
  alreadyApprovedNotice: boolean;
  restoredRevisionActive: boolean;
  onClearRestore: () => void;
}

export function StatusRail({
  score,
  vastuEnabled,
  compliance,
  municipality,
  structStatus,
  structChangelog,
  approvingStructural,
  onApproveStructural,
  onRunStructuralDesign,
  alreadyApprovedNotice,
  restoredRevisionActive,
  onClearRestore,
}: StatusRailProps) {
  // Default open when there's actionable state the user needs to see right away
  // (a compliance failure or a restored-revision preview); otherwise start
  // collapsed so the floor plan stays above the fold.
  const [expanded, setExpanded] = useState(() => !compliance.passed || restoredRevisionActive);
  const structBadge = statusBadgeInfo(structStatus);

  return (
    <div className="rounded-lg border border-border bg-muted/20">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="flex w-full flex-wrap items-center gap-2 px-4 py-2.5 text-left"
      >
        <span
          className={[
            "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold",
            structBadge.tone === "success"
              ? "border-green-500/40 bg-green-500/10 text-green-700 dark:text-green-400"
              : structBadge.tone === "warning"
                ? "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400"
                : structBadge.tone === "info"
                  ? "border-blue-500/40 bg-blue-500/10 text-blue-700 dark:text-blue-400"
                  : "border-border bg-muted text-muted-foreground",
          ].join(" ")}
        >
          {structBadge.label}
        </span>

        {score && (
          <span className="text-xs font-semibold text-foreground">
            Score {score.total.toFixed(0)}/100
          </span>
        )}

        {vastuEnabled && <VastuBadge compliance={compliance} />}

        <span
          className={[
            "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold",
            compliance.passed
              ? "border-green-500/40 bg-green-500/10 text-green-700 dark:text-green-400"
              : "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-400",
          ].join(" ")}
        >
          {compliance.passed ? (
            <Check className="h-3 w-3" aria-hidden="true" />
          ) : (
            <X className="h-3 w-3" aria-hidden="true" />
          )}
          {compliance.passed ? "Compliance passed" : "Compliance failed"}
        </span>

        {restoredRevisionActive && (
          <span className="inline-flex items-center gap-1 rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-xs font-semibold text-amber-700 dark:text-amber-400">
            Restored revision
          </span>
        )}

        <ChevronDown
          className={`ml-auto h-4 w-4 shrink-0 text-muted-foreground transition-transform ${expanded ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
        <span className="sr-only">
          {expanded ? "Collapse status details" : "Expand status details"}
        </span>
      </button>

      {expanded && (
        <div className="flex flex-col gap-3 border-t border-border px-4 py-3">
          {restoredRevisionActive && (
            <div className="flex items-center justify-between rounded-lg border border-amber-500/40 bg-amber-500/8 px-4 py-2.5 text-sm">
              <span className="text-amber-700 dark:text-amber-400 font-medium">
                Viewing a restored revision — this is a preview only, not the current saved state.
              </span>
              <button
                type="button"
                onClick={onClearRestore}
                className="ml-4 shrink-0 rounded-md border border-amber-500/40 px-2 py-1 text-xs text-amber-700 dark:text-amber-400 hover:bg-amber-500/15 transition-colors"
              >
                Back to current
              </button>
            </div>
          )}

          <StructuralLifecycleHeader
            status={structStatus}
            changelog={structChangelog}
            approving={approvingStructural}
            onApprove={onApproveStructural}
            onRunDesign={onRunStructuralDesign}
          />
          {alreadyApprovedNotice && (
            <p className="text-xs text-muted-foreground">Plan was already approved.</p>
          )}

          {score && (
            <TooltipProvider>
              <div className="flex flex-wrap gap-3 rounded-lg border border-border bg-muted/30 px-4 py-3 text-xs">
                <span className="font-semibold text-foreground">
                  Score {score.total.toFixed(0)}/100
                </span>
                {SCORE_FIELDS.map((f) => (
                  <Tooltip key={f.key}>
                    <TooltipTrigger asChild>
                      <span className="text-muted-foreground underline decoration-dotted underline-offset-2 cursor-help">
                        {f.label} {score[f.key].toFixed(0)}
                      </span>
                    </TooltipTrigger>
                    <TooltipContent>{f.tip}</TooltipContent>
                  </Tooltip>
                ))}
              </div>
            </TooltipProvider>
          )}

          {vastuEnabled && (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-muted/20 px-4 py-3">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                Vastu
              </span>
              <VastuBadge compliance={compliance} />
              {score && (
                <span className="text-xs text-muted-foreground">
                  Score: {score.vastu.toFixed(0)}/100
                </span>
              )}
            </div>
          )}

          <div
            className={[
              "flex flex-col gap-1.5 rounded-lg border p-3 text-sm",
              compliance.passed
                ? "border-green-500/40 bg-green-500/8 text-green-700 dark:text-green-400"
                : "border-red-500/40 bg-red-500/8 text-red-700 dark:text-red-400",
            ].join(" ")}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold flex items-center gap-2">
                {compliance.passed ? (
                  <>
                    <Check
                      className="h-4 w-4 text-green-600 dark:text-green-400"
                      aria-hidden="true"
                    />
                    <span>Compliance passed</span>
                    <span className="sr-only">Compliance check passed</span>
                  </>
                ) : (
                  <>
                    <X className="h-4 w-4 text-red-600 dark:text-red-400" aria-hidden="true" />
                    <span>Compliance failed</span>
                    <span className="sr-only">Compliance check failed</span>
                  </>
                )}
              </span>
              {municipality && (
                <span className="text-xs font-normal text-muted-foreground opacity-80">
                  Validated against: {municipality}
                </span>
              )}
            </div>

            {compliance.violations.length > 0 && (
              <ul className="list-inside list-disc space-y-0.5 text-red-600 dark:text-red-400">
                {compliance.violations.map((v) => (
                  <li key={v}>{v}</li>
                ))}
              </ul>
            )}

            {compliance.warnings.length > 0 && (
              <details className="mt-1">
                <summary className="cursor-pointer text-xs text-amber-700 dark:text-amber-400 font-medium">
                  {compliance.warnings.length} warning
                  {compliance.warnings.length !== 1 ? "s" : ""}
                </summary>
                <ul className="mt-1 list-inside list-disc space-y-0.5 text-amber-700 dark:text-amber-400 text-xs">
                  {compliance.warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
