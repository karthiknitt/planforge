"use client";

import { Lock } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { BOQViewer } from "@/components/boq-viewer";
import { FloorPlanSVG } from "@/components/floor-plan-svg";
import { SectionViewSVG } from "@/components/section-view-svg";
import { Button } from "@/components/ui/button";
import { useSession } from "@/lib/auth-client";
import type { GenerateResponse } from "@/lib/layout-types";

const TYPE_LABELS: Record<string, string> = {
  living: "Living / Hall",
  bedroom: "Bedroom",
  kitchen: "Kitchen",
  toilet: "Toilet",
  staircase: "Staircase",
  parking: "Parking",
  utility: "Utility / Other",
  pooja: "Pooja Room",
  study: "Study",
  balcony: "Balcony",
  dining: "Dining",
};

const SWATCH: Record<string, string> = {
  living: "bg-yellow-100 border-yellow-400",
  bedroom: "bg-violet-100 border-violet-500",
  kitchen: "bg-green-100 border-green-600",
  toilet: "bg-sky-100 border-sky-500",
  staircase: "bg-slate-100 border-slate-400",
  parking: "bg-slate-50 border-slate-300",
  utility: "bg-slate-50 border-slate-300",
  pooja: "bg-orange-50 border-orange-400",
  study: "bg-emerald-50 border-emerald-500",
  balcony: "bg-blue-50 border-blue-400",
  dining: "bg-yellow-50 border-yellow-500",
};

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
}: LayoutViewerProps) {
  const { data: session } = useSession();
  const [selectedId, setSelectedId] = useState("A");
  const [floor, setFloor] = useState(0);
  const [activeTab, setActiveTab] = useState<"plan" | "section" | "boq">("plan");
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
  const floorPlan = floor === 0 ? layout.ground_floor : layout.first_floor;
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
              onClick={() => setSelectedId(l.id)}
              className={[
                "rounded-lg border px-4 py-2 text-sm font-medium transition-colors",
                selectedId === l.id
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-transparent hover:bg-muted",
              ].join(" ")}
            >
              Layout {l.id} — {l.name}
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
            {downloadingPdf ? "\u2026" : "PDF"}
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
              {downloadingDxf ? "\u2026" : "DXF"}
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
          {layout.compliance.passed ? "\u2713 Compliance passed" : "\u2717 Compliance failed"}
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

      {/* Tabs: Floor Plan | Section | BOQ */}
      <div className="flex gap-1 rounded-xl border border-border bg-muted/40 p-1 w-fit">
        {(["plan", "section", "boq"] as const).map((tab) => (
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
            {tab === "plan" ? "Floor Plan" : tab === "section" ? "Section View" : "BOQ"}
          </button>
        ))}
      </div>

      {activeTab === "plan" && (
        <div className="flex flex-col gap-3">
          {/* Floor toggle */}
          <div className="flex w-fit items-center gap-1 rounded-xl border border-border bg-muted/40 p-1">
            {[0, 1].map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFloor(f)}
                className={[
                  "rounded-lg px-3 py-1 text-sm font-medium transition-colors",
                  floor === f
                    ? "bg-background text-foreground shadow-sm"
                    : "hover:bg-background/50",
                ].join(" ")}
              >
                {f === 0 ? "Ground floor" : "First floor"}
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
            Parametric section through the building. Dimensions are standard for G+1 Indian
            residential construction.
          </p>
          <SectionViewSVG buildingWidth={plotWidth} className="max-w-xl rounded-xl border" />
          <div className="rounded-lg border bg-muted/40 px-4 py-3 text-xs text-muted-foreground grid grid-cols-2 gap-1 sm:grid-cols-3">
            <span>Floor height: 3.0 m (GF & FF)</span>
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
    </div>
  );
}
