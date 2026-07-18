"use client";

import { useEffect, useRef, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";

// Not an R3F component — DxfViewer manages its own THREE.Scene/renderer
// internally, so it mounts imperatively into a plain div ref. Runs on the
// main thread (no workerFactory) — this project's DXF exports (double-line
// walls, door/window blocks, ANSI31/ANSI37 hatch) are small single-floor
// drawings, not the huge multi-megabyte files dxf-viewer's worker mode
// targets.
export default function DxfPreviewCanvas({ blob }: { blob: Blob }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!containerRef.current) return;
    let cancelled = false;
    let viewer: import("dxf-viewer").DxfViewer | null = null;
    const objectUrl = URL.createObjectURL(blob);

    import("dxf-viewer")
      .then(({ DxfViewer }) => {
        if (cancelled || !containerRef.current) return;
        viewer = new DxfViewer(containerRef.current, { autoResize: true });
        return viewer.Load({ url: objectUrl });
      })
      .then(() => {
        if (!cancelled) setLoading(false);
      })
      .catch(() => {
        if (!cancelled) {
          setFailed(true);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
      URL.revokeObjectURL(objectUrl);
      viewer?.Destroy();
    };
  }, [blob]);

  if (failed) {
    return (
      <p className="text-muted-foreground text-sm">
        Preview unavailable for this drawing — download the DXF to view it in AutoCAD/DraftSight.
      </p>
    );
  }

  return (
    <div className="relative h-[60vh] w-full">
      {loading && <Skeleton className="absolute inset-0" />}
      <div ref={containerRef} className="h-full w-full" />
    </div>
  );
}
