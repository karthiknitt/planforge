"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";

// dxf-viewer touches WebGL/DOM APIs unavailable during SSR.
const DxfPreviewCanvas = dynamic(() => import("./dxf-preview-canvas"), {
  ssr: false,
  loading: () => <Skeleton className="h-[60vh] w-full" />,
});

interface DxfPreviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  fetchDxf: () => Promise<Blob>;
  onDownload: () => void;
  downloading?: boolean;
}

export function DxfPreviewDialog({
  open,
  onOpenChange,
  fetchDxf,
  onDownload,
  downloading = false,
}: DxfPreviewDialogProps) {
  const [blob, setBlob] = useState<Blob | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // fetchDxf is recreated each render by the caller — depending on it would
  // re-fetch on every parent re-render while the dialog stays open. Only
  // `open` should re-trigger the fetch.
  // biome-ignore lint/correctness/useExhaustiveDependencies: fetchDxf intentionally excluded, see comment above
  useEffect(() => {
    if (!open) return;
    setBlob(null);
    setError("");
    setLoading(true);
    let cancelled = false;
    fetchDxf()
      .then((b) => {
        if (!cancelled) setBlob(b);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load preview");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>DXF preview</DialogTitle>
        </DialogHeader>

        {loading && <Skeleton className="h-[60vh] w-full" />}

        {error && <p className="text-sm text-destructive">{error}</p>}

        {blob && !loading && <DxfPreviewCanvas blob={blob} />}

        <div className="flex justify-end">
          <Button onClick={onDownload} disabled={downloading}>
            {downloading ? "Downloading…" : "Download DXF"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
