"use client";

import { Lock } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { BOQViewer } from "@/components/boq-viewer";
import { ChatPanel } from "@/components/chat-panel";
import { FloorPlanSVG } from "@/components/floor-plan-svg";
import { SectionViewSVG } from "@/components/section-view-svg";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useSession } from "@/lib/auth-client";
import type { FloorPlanData, GenerateResponse, LayoutData } from "@/lib/layout-types";

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

interface LayoutViewerProps {
  generateData: GenerateResponse | null;
  plotWidth: number;
  plotLength: number;
  roadSide: string;
  northDirection: string;
  projectId: string;
  planTier: string;
  plotShape?: string;
  plotFrontWidth?: number;
  plotRearWidth?: number;
  numFloors?: number;
}

export function LayoutViewer({
  generateData,
  plotWidth,
  plotLength,
  roadSide,
  projectId,
  planTier,
  plotShape,
  plotFrontWidth,
  plotRearWidth,
  numFloors = 1,
}: LayoutViewerProps) {
  const { data: session } = useSession();
  const [selectedId, setSelectedId] = useState("A");
  const [floor, setFloor] = useState(0);
  const [activeTab, setActiveTab] = useState<"plan" | "section" | "boq" | "chat">("plan");
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [downloadingDxf, setDownloadingDxf] = useState(false);
  const [downloadError, setDownloadError] = useState("");

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

  const layout = generateData.layouts.find((l) => l.id === selectedId) ?? generateData.layouts[0];

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
            </button>
          ))}
        </div>

        {/* Export buttons */}
        <div className="flex gap-2">
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
        </div>
      </div>

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

      {/* Tabs: Floor Plan | Section | BOQ | Chat */}
      <div className="flex gap-1 rounded-xl border border-border bg-muted/40 p-1 w-fit">
        {(["plan", "section", "boq", "chat"] as const).map((tab) => (
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

          <FloorPlanSVG
            floorPlan={floorPlan}
            plotWidth={plotWidth}
            plotLength={plotLength}
            roadSide={roadSide}
            className="max-w-xl rounded-xl border"
            plotShape={plotShape}
            plotFrontWidth={plotFrontWidth}
            plotRearWidth={plotRearWidth}
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

      {activeTab === "chat" &&
        (planTier === "pro" ? (
          <ChatPanel projectId={projectId} currentLayout={layout} />
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
