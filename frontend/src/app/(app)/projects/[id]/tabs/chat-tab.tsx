"use client";

import { Lock } from "lucide-react";
import Link from "next/link";

import { ChatPanel } from "@/components/chat-panel";
import { FloorPlanSVG } from "@/components/floor-plan-svg";
import { Button } from "@/components/ui/button";
import type { LayoutData } from "@/lib/layout-types";
import type { Locale } from "@/lib/locale-context";
import { tierAtLeast } from "@/lib/plan";

export function ChatTab({
  projectId,
  planTier,
  layout,
  floor,
  liveLayout,
  plotXExtent,
  plotYExtent,
  roadSide,
  plotShape,
  plotFrontWidth,
  plotRearWidth,
  plotCorners,
  cutoutCorner,
  cutoutWidth,
  cutoutHeight,
  locale,
  onLayoutUpdate,
}: {
  projectId: string;
  planTier: string;
  layout: LayoutData;
  floor: number;
  liveLayout: LayoutData | null;
  plotXExtent: number;
  plotYExtent: number;
  roadSide?: string;
  plotShape?: string;
  plotFrontWidth?: number;
  plotRearWidth?: number;
  plotCorners?: [number, number][];
  cutoutCorner?: string;
  cutoutWidth?: number;
  cutoutHeight?: number;
  locale: Locale;
  onLayoutUpdate: (updated: LayoutData) => void;
}) {
  if (!tierAtLeast(planTier, "pro")) {
    return (
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
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {/* Left: live floor plan preview — hidden on mobile to save screen space */}
      <div className="hidden md:flex flex-col gap-2">
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
          plotXExtent={plotXExtent}
          plotYExtent={plotYExtent}
          roadSide={roadSide}
          className="rounded-xl border"
          plotShape={plotShape}
          plotFrontWidth={plotFrontWidth}
          plotRearWidth={plotRearWidth}
          plotCorners={plotCorners}
          cutoutCorner={cutoutCorner}
          cutoutWidth={cutoutWidth}
          cutoutHeight={cutoutHeight}
          locale={locale}
        />
        <p className="text-xs text-muted-foreground">
          Showing {floor === 1 ? "First" : "Ground"} Floor — switches in the Floor Plan tab
        </p>
      </div>
      {/* Right: chat panel */}
      <ChatPanel projectId={projectId} currentLayout={layout} onLayoutUpdate={onLayoutUpdate} />
    </div>
  );
}
