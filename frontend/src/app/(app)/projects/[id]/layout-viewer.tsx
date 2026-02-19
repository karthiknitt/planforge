"use client";

import { useState } from "react";

import { FloorPlanSVG } from "@/components/floor-plan-svg";
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
};

const SWATCH: Record<string, string> = {
  living: "bg-yellow-100 border-yellow-400",
  bedroom: "bg-violet-100 border-violet-500",
  kitchen: "bg-green-100 border-green-600",
  toilet: "bg-sky-100 border-sky-500",
  staircase: "bg-slate-100 border-slate-400",
  parking: "bg-slate-50 border-slate-300",
  utility: "bg-slate-50 border-slate-300",
};

interface LayoutViewerProps {
  generateData: GenerateResponse | null;
  plotWidth: number;
  plotLength: number;
  roadSide: string;
  northDirection: string;
  projectId: string;
}

export function LayoutViewer({
  generateData,
  plotWidth,
  plotLength,
  roadSide,
  projectId,
}: LayoutViewerProps) {
  const { data: session } = useSession();
  const [selectedId, setSelectedId] = useState("A");
  const [floor, setFloor] = useState(0); // 0 = ground, 1 = first
  const [downloading, setDownloading] = useState(false);

  async function handleDownload() {
    if (!session) return;
    setDownloading(true);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/export/pdf?layout_id=${selectedId}`,
        { headers: { "X-User-Id": session.user.id } }
      );
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `planforge-layout-${selectedId}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } finally {
      setDownloading(false);
    }
  }

  if (!generateData) {
    return (
      <div className="rounded-xl border border-dashed p-12 text-center text-muted-foreground">
        <p className="font-medium">Layout engine offline</p>
        <p className="mt-1 text-sm">
          Start the backend server and refresh to see floor plans.
        </p>
      </div>
    );
  }

  const layout =
    generateData.layouts.find((l) => l.id === selectedId) ??
    generateData.layouts[0];
  const floorPlan = floor === 0 ? layout.ground_floor : layout.first_floor;
  const presentTypes = [...new Set(floorPlan.rooms.map((r) => r.type))];

  return (
    <div className="flex flex-col gap-6">
      {/* Layout selector tabs + download button */}
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
                  ? "border-foreground bg-foreground text-background"
                  : "border-border bg-background hover:bg-muted",
              ].join(" ")}
            >
              Layout {l.id} — {l.name}
            </button>
          ))}
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleDownload}
          disabled={downloading || !session}
        >
          {downloading ? "Downloading…" : "Download PDF"}
        </Button>
      </div>

      {/* Compliance badge */}
      <div
        className={[
          "flex flex-col gap-1.5 rounded-lg border p-3 text-sm",
          layout.compliance.passed
            ? "border-green-300 bg-green-50"
            : "border-red-300 bg-red-50",
        ].join(" ")}
      >
        <span
          className={[
            "font-semibold",
            layout.compliance.passed ? "text-green-700" : "text-red-700",
          ].join(" ")}
        >
          {layout.compliance.passed ? "✓ Compliance passed" : "✗ Compliance failed"}
        </span>

        {layout.compliance.violations.length > 0 && (
          <ul className="list-inside list-disc space-y-0.5 text-red-700">
            {layout.compliance.violations.map((v, i) => (
              <li key={i}>{v}</li>
            ))}
          </ul>
        )}

        {layout.compliance.warnings.length > 0 && (
          <ul className="list-inside list-disc space-y-0.5 text-amber-700">
            {layout.compliance.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        )}
      </div>

      {/* Floor toggle + SVG */}
      <div className="flex flex-col gap-3">
        <div className="flex w-fit items-center gap-1 rounded-lg border border-border bg-muted p-1">
          {[0, 1].map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFloor(f)}
              className={[
                "rounded-md px-3 py-1 text-sm font-medium transition-colors",
                floor === f ? "bg-background shadow-sm" : "hover:bg-background/50",
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
        />
      </div>

      {/* Room type legend */}
      <div className="flex flex-wrap gap-3">
        {presentTypes.map((type) => (
          <div key={type} className="flex items-center gap-1.5">
            <div
              className={[
                "size-3 rounded-sm border",
                SWATCH[type] ?? SWATCH.utility,
              ].join(" ")}
            />
            <span className="text-xs text-muted-foreground">
              {TYPE_LABELS[type] ?? type}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
