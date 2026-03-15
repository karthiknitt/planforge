"use client";

import { Check, Copy, Link2, Lock } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { BOQViewer } from "@/components/boq-viewer";
import { ChatPanel } from "@/components/chat-panel";
import { FloorPlanSVG } from "@/components/floor-plan-svg";
import { LayoutCompareView } from "@/components/layout-compare-view";
import { SectionViewSVG } from "@/components/section-view-svg";
import { ShareWhatsAppButton } from "@/components/share-whatsapp-button";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useSession } from "@/lib/auth-client";
import type {
  ComplianceData,
  FloorPlanData,
  GenerateResponse,
  LayoutData,
} from "@/lib/layout-types";

const TYPE_LABELS: Record<string, string> = {
  living: "Living / Hall",
  bedroom: "Bedroom",
  master_bedroom: "Master Bedroom",
  kitchen: "Kitchen",
  toilet: "Toilet",
  staircase: "Staircase",
  parking: "Parking",
  utility: "Utility / Other",
  pooja: "Pooja Room",
  study: "Study",
  balcony: "Balcony",
  dining: "Dining",
  servant_quarter: "Servant Quarter",
  home_office: "Home Office",
  gym: "Gym",
  store_room: "Store Room",
  garage: "Garage",
  passage: "Passage",
};

const SWATCH: Record<string, string> = {
  living: "bg-yellow-100 border-yellow-400",
  bedroom: "bg-violet-100 border-violet-500",
  master_bedroom: "bg-purple-100 border-purple-500",
  kitchen: "bg-green-100 border-green-600",
  toilet: "bg-sky-100 border-sky-500",
  staircase: "bg-slate-100 border-slate-400",
  parking: "bg-slate-50 border-slate-300",
  utility: "bg-slate-50 border-slate-300",
  pooja: "bg-orange-50 border-orange-400",
  study: "bg-emerald-50 border-emerald-500",
  balcony: "bg-blue-50 border-blue-400",
  dining: "bg-yellow-50 border-yellow-500",
  servant_quarter: "bg-orange-50 border-orange-500",
  home_office: "bg-green-50 border-green-500",
  gym: "bg-red-50 border-red-400",
  store_room: "bg-slate-50 border-slate-400",
  garage: "bg-blue-50 border-blue-500",
  passage: "bg-slate-100 border-slate-400",
};

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 75
      ? "bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/40"
      : score >= 55
        ? "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/40"
        : "bg-red-500/15 text-red-700 dark:text-red-400 border-red-500/40";
  return (
    <span className={`ml-1.5 rounded-md border px-1.5 py-0.5 text-xs font-semibold ${color}`}>
      {score.toFixed(0)}
    </span>
  );
}

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

interface LayoutViewerProps {
  generateData: GenerateResponse | null;
  plotWidth: number;
  plotLength: number;
  roadSide: string;
  northDirection: string;
  projectId: string;
  projectName: string;
  planTier: string;
  plotShape?: string;
  plotFrontWidth?: number;
  plotRearWidth?: number;
  plotCorners?: [number, number][];
  numFloors?: number;
  vastuEnabled?: boolean;
}

// ── Vastu badge helper ────────────────────────────────────────────────────────
function _VastuBadge({ compliance }: { compliance: ComplianceData }) {
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

export function LayoutViewer({
  generateData,
  plotWidth,
  plotLength,
  roadSide,
  projectId,
  projectName,
  planTier,
  plotShape,
  plotFrontWidth,
  plotRearWidth,
  plotCorners,
  numFloors: _numFloors = 1,
  vastuEnabled = false,
}: LayoutViewerProps) {
  const { data: session } = useSession();
  // Use the first layout's actual ID — IDs may be "S1","S2","D" etc, never assume "A"
  const [selectedId, setSelectedId] = useState(() => generateData?.layouts[0]?.id ?? "A");
  const [liveLayout, setLiveLayout] = useState<LayoutData | null>(null);
  const [floor, setFloor] = useState(0);
  const [activeTab, setActiveTab] = useState<"plan" | "section" | "boq" | "chat" | "compare">(
    "plan"
  );
  const [_showVastuZones, _setShowVastuZones] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [downloadingDxf, setDownloadingDxf] = useState(false);
  const [downloadError, setDownloadError] = useState("");
  const [shareOpen, setShareOpen] = useState(false);
  const [shareUrl, setShareUrl] = useState("");
  const [shareLoading, setShareLoading] = useState(false);
  const [shareError, setShareError] = useState("");
  const [copied, setCopied] = useState(false);

  async function handleShare() {
    if (!session) return;
    setShareLoading(true);
    setShareError("");
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/share`,
        { method: "POST", headers: { "X-User-Id": session.user.id } }
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail ?? `Failed to generate share link (${res.status})`);
      }
      const json = await res.json();
      const fullUrl = `${window.location.origin}${json.share_url}`;
      setShareUrl(fullUrl);
      setShareOpen(true);
    } catch (err) {
      setShareError(err instanceof Error ? err.message : "Could not generate share link");
    } finally {
      setShareLoading(false);
    }
  }

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback: select the input text
    }
  }

  async function handleDownload(format: "pdf" | "dxf") {
    if (!session) return;
    const setter = format === "pdf" ? setDownloadingPdf : setDownloadingDxf;
    setter(true);
    setDownloadError("");
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/export/${format}?layout_id=${selectedId}`,
        { headers: { "X-User-Id": session.user.id } }
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail ?? `Export failed (${res.status})`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `planforge-layout-${selectedId}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setDownloadError(
        err instanceof Error ? err.message : "Download failed — is the backend running?"
      );
    } finally {
      setter(false);
    }
  }

  if (!generateData) {
    return (
      <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground">
        <p className="font-medium">Layout engine offline</p>
        <p className="mt-1 text-sm">Start the backend server and refresh to see floor plans.</p>
      </div>
    );
  }

  if (generateData.layouts.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground">
        <p className="font-medium">No compliant layouts could be generated</p>
        <p className="mt-1 text-sm">
          The plot configuration does not produce any layouts that satisfy the building compliance
          rules. Try increasing the plot size or reducing the setbacks.
        </p>
      </div>
    );
  }

  const baseLayout =
    generateData.layouts.find((l) => l.id === selectedId) ?? generateData.layouts[0];
  const layout = liveLayout ?? baseLayout;

  // Build the ordered list of available floors for this layout
  const availableFloors: { label: string; index: number; plan: FloorPlanData }[] = [];
  if (layout.basement_floor)
    availableFloors.push({ label: "Basement", index: -1, plan: layout.basement_floor });
  availableFloors.push({
    label: layout.ground_floor.floor_type === "stilt" ? "Stilt Floor" : "Ground Floor",
    index: 0,
    plan: layout.ground_floor,
  });
  availableFloors.push({ label: "First Floor", index: 1, plan: layout.first_floor });
  if (layout.second_floor)
    availableFloors.push({ label: "Second Floor", index: 2, plan: layout.second_floor });

  const currentFloorEntry = availableFloors.find((f) => f.index === floor) ?? availableFloors[1];
  const floorPlan = currentFloorEntry.plan;
  const presentTypes = [...new Set(floorPlan.rooms.map((r) => r.type))];

  return (
    <div className="flex flex-col gap-6">
      {/* Layout selector + export buttons */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-2">
          {generateData.layouts.map((l) => (
            <button
              key={l.id}
              type="button"
              onClick={() => {
                setSelectedId(l.id);
                setFloor(0);
                setLiveLayout(null);
              }}
              className={[
                "rounded-lg border px-4 py-2 text-sm font-medium transition-colors",
                selectedId === l.id
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-transparent hover:bg-muted",
              ].join(" ")}
            >
              Layout {l.id} — {l.name}
              {l.score && <ScoreBadge score={l.score.total} />}
              {vastuEnabled && (
                <span
                  className={[
                    "ml-1 rounded-sm border px-1 py-0.5 text-xs",
                    l.compliance.violations.some((v) => v.startsWith("[Vastu]"))
                      ? "border-red-500/40 bg-red-500/10 text-red-600 dark:text-red-400"
                      : l.compliance.warnings.some((w) => w.startsWith("[Vastu]"))
                        ? "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400"
                        : "border-green-500/40 bg-green-500/10 text-green-600 dark:text-green-400",
                  ].join(" ")}
                >
                  {l.compliance.violations.some((v) => v.startsWith("[Vastu]"))
                    ? "Vastu ✗"
                    : l.compliance.warnings.some((w) => w.startsWith("[Vastu]"))
                      ? "Vastu ⚠"
                      : "Vastu ✓"}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Export + share buttons */}
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            className="border-border text-foreground hover:bg-muted"
            onClick={() => handleDownload("pdf")}
            disabled={downloadingPdf || !session}
          >
            {downloadingPdf ? "…" : "PDF"}
          </Button>
          {planTier === "free" ? (
            <Button
              variant="outline"
              size="sm"
              className="border-border text-foreground hover:bg-muted"
              asChild
              title="Upgrade to Basic for DXF export"
            >
              <Link href="/pricing">
                <Lock className="h-3 w-3 mr-1.5" />
                DXF
              </Link>
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              className="border-border text-foreground hover:bg-muted"
              onClick={() => handleDownload("dxf")}
              disabled={downloadingDxf || !session}
              title="DXF for AutoCAD / DraftSight"
            >
              {downloadingDxf ? "…" : "DXF"}
            </Button>
          )}
          <ShareWhatsAppButton projectName={projectName} layoutId={selectedId} />
          <Button
            variant="outline"
            size="sm"
            className="border-border text-foreground hover:bg-muted"
            onClick={handleShare}
            disabled={shareLoading || !session}
            title="Get a read-only share link for your client"
          >
            <Link2 className="h-3 w-3 mr-1.5" />
            {shareLoading ? "…" : "Share"}
          </Button>
        </div>
      </div>

      {/* Share error */}
      {shareError && (
        <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {shareError}
        </p>
      )}

      {/* Share link dialog */}
      <Dialog open={shareOpen} onOpenChange={setShareOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Share floor plan with client</DialogTitle>
            <DialogDescription>
              Anyone with this link can view the floor plans in read-only mode — no login required.
            </DialogDescription>
          </DialogHeader>
          <div className="flex items-center gap-2 mt-2">
            <input
              readOnly
              value={shareUrl}
              className="flex-1 rounded-lg border border-border bg-muted px-3 py-2 text-sm font-mono text-foreground"
              onFocus={(e) => e.target.select()}
            />
            <Button
              size="sm"
              variant="outline"
              onClick={handleCopy}
              className="shrink-0"
              title="Copy link"
            >
              {copied ? <Check className="h-4 w-4 text-green-600" /> : <Copy className="h-4 w-4" />}
            </Button>
          </div>
          {copied && (
            <p className="text-xs text-green-600 dark:text-green-400">Copied to clipboard!</p>
          )}
          <p className="text-xs text-muted-foreground">
            The link shows all layout options with floor plans, section view, and compliance status.
          </p>
        </DialogContent>
      </Dialog>

      {/* Download error */}
      {downloadError && (
        <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {downloadError}
        </p>
      )}

      {/* Score breakdown for selected layout */}
      {layout.score && (
        <div className="flex flex-wrap gap-3 rounded-lg border border-border bg-muted/30 px-4 py-3 text-xs">
          <span className="font-semibold text-foreground">
            Score {layout.score.total.toFixed(0)}/100
          </span>
          <span className="text-muted-foreground">
            Light {layout.score.natural_light.toFixed(0)}
          </span>
          <span className="text-muted-foreground">Adj {layout.score.adjacency.toFixed(0)}</span>
          <span className="text-muted-foreground">AR {layout.score.aspect_ratio.toFixed(0)}</span>
          <span className="text-muted-foreground">Fill {layout.score.circulation.toFixed(0)}</span>
          <span className="text-muted-foreground">Vastu {layout.score.vastu.toFixed(0)}</span>
        </div>
      )}

      {/* Vastu compliance summary (shown only when vastu_enabled) */}
      {vastuEnabled && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-muted/20 px-4 py-3">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Vastu
          </span>
          <VastuBadge compliance={layout.compliance} />
          {layout.score && (
            <span className="text-xs text-muted-foreground">
              Score: {layout.score.vastu.toFixed(0)}/100
            </span>
          )}
        </div>
      )}

      {/* Compliance badge */}
      <div
        className={[
          "flex flex-col gap-1.5 rounded-lg border p-3 text-sm",
          layout.compliance.passed
            ? "border-green-500/40 bg-green-500/8 text-green-700 dark:text-green-400"
            : "border-red-500/40 bg-red-500/8 text-red-700 dark:text-red-400",
        ].join(" ")}
      >
        <span className="font-semibold">
          {layout.compliance.passed ? "✓ Compliance passed" : "✗ Compliance failed"}
        </span>

        {layout.compliance.violations.length > 0 && (
          <ul className="list-inside list-disc space-y-0.5 text-red-600 dark:text-red-400">
            {layout.compliance.violations.map((v) => (
              <li key={v}>{v}</li>
            ))}
          </ul>
        )}

        {layout.compliance.warnings.length > 0 && (
          <details className="mt-1">
            <summary className="cursor-pointer text-xs text-amber-700 dark:text-amber-400 font-medium">
              {layout.compliance.warnings.length} warning
              {layout.compliance.warnings.length !== 1 ? "s" : ""}
            </summary>
            <ul className="mt-1 list-inside list-disc space-y-0.5 text-amber-700 dark:text-amber-400 text-xs">
              {layout.compliance.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </details>
        )}
      </div>

      {/* Space utilisation notes */}
      {layout.space_notes && layout.space_notes.length > 0 && (
        <details className="rounded-lg border border-blue-400/30 bg-blue-500/8 p-3 text-sm">
          <summary className="cursor-pointer font-medium text-blue-700 dark:text-blue-400">
            ℹ️ {layout.space_notes.length} space optimisation
            {layout.space_notes.length !== 1 ? "s" : ""} applied
          </summary>
          <ul className="mt-2 list-inside list-disc space-y-1 text-blue-700/80 dark:text-blue-400/80 text-xs">
            {layout.space_notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </details>
      )}

      {/* Tabs: Floor Plan | Section | BOQ | Compare | Chat */}
      <div className="flex gap-1 rounded-xl border border-border bg-muted/40 p-1 w-fit">
        {(["plan", "section", "boq", "compare", "chat"] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={[
              "rounded-lg px-4 py-1.5 text-sm font-medium transition-colors",
              activeTab === tab
                ? "bg-background text-foreground shadow-sm"
                : "hover:bg-background/50",
            ].join(" ")}
          >
            {tab === "plan"
              ? "Floor Plan"
              : tab === "section"
                ? "Section View"
                : tab === "boq"
                  ? "BOQ"
                  : tab === "compare"
                    ? "Compare"
                    : "Chat"}
          </button>
        ))}
      </div>

      {activeTab === "plan" && (
        <div className="flex flex-col gap-3">
          {/* Dynamic floor toggle */}
          <div className="flex w-fit items-center gap-1 rounded-xl border border-border bg-muted/40 p-1">
            {availableFloors.map((f) => (
              <button
                key={f.index}
                type="button"
                onClick={() => setFloor(f.index)}
                className={[
                  "rounded-lg px-3 py-1 text-sm font-medium transition-colors",
                  floor === f.index
                    ? "bg-background text-foreground shadow-sm"
                    : "hover:bg-background/50",
                ].join(" ")}
              >
                {f.label}
                {f.plan.needs_mech_ventilation && (
                  <span
                    className="ml-1 text-xs text-amber-600"
                    title="Mechanical ventilation required"
                  >
                    ⚠
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Vastu zone overlay toggle */}
          {vastuEnabled && (
            <button
              type="button"
              onClick={() => setShowVastuZones((v) => !v)}
              className={[
                "flex w-fit items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
                showVastuZones
                  ? "border-orange-500/60 bg-orange-500/10 text-orange-700 dark:text-orange-400"
                  : "border-border bg-transparent text-muted-foreground hover:bg-muted",
              ].join(" ")}
            >
              {showVastuZones ? "Hide Vastu Zones" : "Show Vastu Zones"}
            </button>
          )}

          <FloorPlanSVG
            floorPlan={floorPlan}
            plotWidth={plotWidth}
            plotLength={plotLength}
            roadSide={roadSide}
            className="max-w-xl rounded-xl border"
            plotShape={plotShape}
            plotFrontWidth={plotFrontWidth}
            plotRearWidth={plotRearWidth}
            plotCorners={plotCorners}
            showVastuZones={showVastuZones}
          />

          {/* Room legend */}
          <div className="flex flex-wrap gap-3">
            {presentTypes.map((type) => (
              <div key={type} className="flex items-center gap-1.5">
                <div
                  className={["size-3 rounded-sm border", SWATCH[type] ?? SWATCH.utility].join(" ")}
                />
                <span className="text-xs text-muted-foreground">{TYPE_LABELS[type] ?? type}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === "section" && (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-muted-foreground">
            Parametric section through the building. Dimensions are standard for Indian residential
            construction.
          </p>
          <SectionViewSVG buildingWidth={plotWidth} className="max-w-xl rounded-xl border" />
          <div className="rounded-lg border bg-muted/40 px-4 py-3 text-xs text-muted-foreground grid grid-cols-2 gap-1 sm:grid-cols-3">
            <span>Floor height: 3.0 m (each floor)</span>
            <span>Slab thickness: 150 mm (RCC)</span>
            <span>Parapet: 1.0 m above roof</span>
            <span>External wall: 230 mm brick</span>
            <span>Foundation: 600 mm below GL</span>
            <span>Stair: 17R x 175 mm riser</span>
          </div>
        </div>
      )}

      {activeTab === "boq" && (
        <BOQViewer projectId={projectId} layoutId={selectedId} planTier={planTier} />
      )}

      {activeTab === "compare" && (
        <LayoutCompareView
          layouts={generateData.layouts}
          plotWidth={plotWidth}
          plotLength={plotLength}
          roadSide={roadSide}
          plotShape={plotShape}
          plotFrontWidth={plotFrontWidth}
          plotRearWidth={plotRearWidth}
          plotCorners={plotCorners}
        />
      )}

      {activeTab === "chat" &&
        (planTier === "pro" ? (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* Left: live floor plan preview */}
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium">Live Layout Preview</p>
                {liveLayout && (
                  <span className="text-xs text-green-600 dark:text-green-400 font-medium">
                    ● AI updated
                  </span>
                )}
              </div>
              <FloorPlanSVG
                floorPlan={floor === 1 ? layout.first_floor : layout.ground_floor}
                plotWidth={plotWidth}
                plotLength={plotLength}
                roadSide={roadSide}
                className="rounded-xl border"
                plotShape={plotShape}
                plotFrontWidth={plotFrontWidth}
                plotRearWidth={plotRearWidth}
                plotCorners={plotCorners}
              />
              <p className="text-xs text-muted-foreground">
                Showing {floor === 1 ? "First" : "Ground"} Floor — switches in the Floor Plan tab
              </p>
            </div>
            {/* Right: chat panel */}
            <ChatPanel
              projectId={projectId}
              currentLayout={layout}
              onLayoutUpdate={(updated) => setLiveLayout(updated)}
            />
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-amber-500/40 bg-amber-500/5 p-8 text-center">
            <Lock className="mx-auto mb-3 h-6 w-6 text-amber-600" />
            <p className="font-semibold text-amber-700 dark:text-amber-400">Pro plan required</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Conversational layout editing with AI is a Pro feature.
            </p>
            <Button asChild className="mt-4" size="sm" variant="outline">
              <Link href="/pricing">Upgrade to Pro</Link>
            </Button>
          </div>
        ))}
    </div>
  );
}
