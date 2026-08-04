"use client";

import { RefreshCw } from "lucide-react";
import type { Plan3DView } from "@/components/plan-3d-scene";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { LayoutData } from "@/lib/layout-types";
import type { RenderSourceFallbackReason } from "@/lib/structural-status";
import { renderSourceFallbackNote } from "@/lib/structural-status";

interface FloorEntry {
  label: string;
  index: number;
}

export function R3fTab({
  structuralDesigned,
  renderSource,
  onRenderSourceChange,
  structuralGeometryLoading,
  structuralGeometry,
  structuralGeometryFallback,
  availableFloors,
  floor,
  onFloorChange,
  r3fView,
  onR3fViewChange,
  r3fPng,
  currentFloorLabel,
  onRefreshCapture,
  onGenerateAiRender,
}: {
  structuralDesigned: boolean;
  renderSource: "architectural" | "structural";
  onRenderSourceChange: (source: "architectural" | "structural") => void;
  structuralGeometryLoading: boolean;
  structuralGeometry: LayoutData | null;
  structuralGeometryFallback: RenderSourceFallbackReason | null;
  availableFloors: FloorEntry[];
  floor: number;
  onFloorChange: (floor: number) => void;
  r3fView: Plan3DView;
  onR3fViewChange: (view: Plan3DView) => void;
  r3fPng: string | null | undefined;
  currentFloorLabel: string;
  onRefreshCapture: () => void;
  onGenerateAiRender: () => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-muted-foreground">
        Geometric plan view of the selected floor, built from the exact plan dimensions. Use it to
        condition the photorealistic AI render — one render per floor.
      </p>
      {structuralDesigned && (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-muted-foreground">Geometry source:</span>
          <Button
            size="sm"
            variant={renderSource === "architectural" ? "default" : "outline"}
            onClick={() => onRenderSourceChange("architectural")}
          >
            Architectural
          </Button>
          <Button
            size="sm"
            variant={renderSource === "structural" ? "default" : "outline"}
            onClick={() => onRenderSourceChange("structural")}
            disabled={structuralGeometryLoading}
          >
            {structuralGeometryLoading ? "Loading…" : "Structural"}
          </Button>
          {renderSource === "structural" && structuralGeometry && (
            <span className="text-green-600 dark:text-green-400">
              Showing the structural design&apos;s adjusted geometry.
            </span>
          )}
          {renderSource === "structural" &&
            !structuralGeometry &&
            !structuralGeometryLoading &&
            structuralGeometryFallback && (
              <span className="text-amber-600 dark:text-amber-400">
                {renderSourceFallbackNote(structuralGeometryFallback)}
              </span>
            )}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {availableFloors.map((f) => (
          <Button
            key={f.index}
            size="sm"
            variant={floor === f.index ? "default" : "outline"}
            onClick={() => onFloorChange(f.index)}
          >
            {f.label}
          </Button>
        ))}
        <span className="mx-1 h-5 w-px bg-border" aria-hidden />
        <Button
          size="sm"
          variant={r3fView === "top" ? "default" : "outline"}
          onClick={() => onR3fViewChange("top")}
        >
          Plan view
        </Button>
        <Button
          size="sm"
          variant={r3fView === "iso" ? "default" : "outline"}
          onClick={() => onR3fViewChange("iso")}
        >
          3D view
        </Button>
      </div>
      {/* No documented fixed output size for this canvas capture — 4:3 is a sensible default that keeps the skeleton and loaded capture the same box. */}
      <div className="aspect-[4/3] w-full max-w-xl overflow-hidden rounded-xl border bg-muted/30">
        {r3fPng ? (
          // biome-ignore lint/performance/noImgElement: captured canvas PNG, not a next/image candidate
          <img
            src={r3fPng}
            alt={`Geometric view — ${currentFloorLabel}`}
            className="h-full w-full object-contain"
          />
        ) : (
          <Skeleton className="h-full w-full rounded-none" />
        )}
      </div>
      <div className="flex w-fit flex-wrap gap-2">
        <Button size="sm" variant="outline" className="gap-1.5" onClick={onRefreshCapture}>
          <RefreshCw className="h-3 w-3" />
          Refresh view
        </Button>
        <Button size="sm" className="gap-1.5" onClick={onGenerateAiRender}>
          Generate AI Render — {currentFloorLabel}
        </Button>
      </div>
    </div>
  );
}
