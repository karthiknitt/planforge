"use client";

import { useTheme } from "next-themes";
import { useEffect, useRef, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";

// Matches --svg-bg light/dark from globals.css. dxf-viewer's clearColor
// takes a THREE.Color, not a CSS var — it paints its own WebGL canvas
// outside the DOM/CSS cascade, so these have to be duplicated here rather
// than read from the stylesheet.
const DXF_BG_LIGHT = "#f8fafc";
const DXF_BG_DARK = "#0d1529";

// Not an R3F component — DxfViewer manages its own THREE.Scene/renderer
// internally, so it mounts imperatively into a plain div ref. Runs on the
// main thread (no workerFactory) — this project's DXF exports (double-line
// walls, door/window blocks, ANSI31/ANSI37 hatch) are small single-floor
// drawings, not the huge multi-megabyte files dxf-viewer's worker mode
// targets.
export default function DxfPreviewCanvas({ blob }: { blob: Blob }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<import("dxf-viewer").DxfViewer | null>(null);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(true);
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const isDark = mounted && resolvedTheme === "dark";

  // isDark intentionally excluded from deps — theme flips while a viewer is
  // already mounted are handled by the setClearColor effect below, without
  // re-parsing the DXF from scratch.
  // biome-ignore lint/correctness/useExhaustiveDependencies: see comment above
  useEffect(() => {
    if (!containerRef.current) return;
    let cancelled = false;
    let viewer: import("dxf-viewer").DxfViewer | null = null;
    const objectUrl = URL.createObjectURL(blob);

    Promise.all([import("dxf-viewer"), import("three")])
      .then(([{ DxfViewer }, { Color }]) => {
        if (cancelled || !containerRef.current) return;
        viewer = new DxfViewer(containerRef.current, {
          autoResize: true,
          clearColor: new Color(isDark ? DXF_BG_DARK : DXF_BG_LIGHT),
        });
        viewerRef.current = viewer;
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
      viewerRef.current = null;
    };
  }, [blob]);

  // Live theme toggle: repaint the existing renderer's clear color instead
  // of remounting the whole viewer (which would re-fetch/re-parse the DXF).
  useEffect(() => {
    const viewer = viewerRef.current;
    const renderer = viewer?.GetRenderer();
    if (!renderer) return;
    import("three").then(({ Color }) => {
      renderer.setClearColor(new Color(isDark ? DXF_BG_DARK : DXF_BG_LIGHT));
      viewer?.Render();
    });
  }, [isDark]);

  if (failed) {
    return (
      <p className="text-muted-foreground text-sm">
        Preview unavailable for this drawing — download the DXF to view it in AutoCAD/DraftSight.
      </p>
    );
  }

  return (
    <div className="relative h-[60vh] w-full" role="img" aria-label="DXF CAD drawing preview">
      {loading && <Skeleton className="absolute inset-0" />}
      <div ref={containerRef} className="h-full w-full" />
    </div>
  );
}
