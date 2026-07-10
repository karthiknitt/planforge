"use client";

import { computePlotPreview, type PlotPreviewInput } from "@/lib/plot-preview";

export function PlotPreview({ input }: { input: PlotPreviewInput }) {
  const g = computePlotPreview(input);
  if (!g.valid) {
    return (
      <div className="flex h-[260px] items-center justify-center rounded-md border border-dashed text-xs text-muted-foreground">
        Enter plot dimensions to preview
      </div>
    );
  }
  return (
    <svg
      viewBox={`0 0 ${g.viewW} ${g.viewH}`}
      className="h-[260px] w-full rounded-md border bg-muted/20"
      role="img"
      aria-label="Plot preview with setbacks"
    >
      {g.road && <rect {...boxProps(g.road)} className="fill-amber-500/60" rx={2} />}
      {g.plot && (
        <rect
          {...boxProps(g.plot)}
          className="fill-transparent stroke-foreground/70"
          strokeWidth={1.5}
        />
      )}
      {g.buildable && (
        <rect
          {...boxProps(g.buildable)}
          className="fill-primary/10 stroke-primary"
          strokeWidth={1}
          strokeDasharray="4 3"
        />
      )}
      {g.buildable && (
        <text
          x={g.buildable.x + g.buildable.w / 2}
          y={g.buildable.y + g.buildable.h / 2}
          textAnchor="middle"
          dominantBaseline="middle"
          className="fill-muted-foreground text-[9px]"
        >
          buildable
        </text>
      )}
    </svg>
  );
}

function boxProps(b: { x: number; y: number; w: number; h: number }) {
  return { x: b.x, y: b.y, width: b.w, height: b.h };
}
