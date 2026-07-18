"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { showErrorToast } from "@/lib/toast";

// react-pdf touches DOM/canvas APIs that don't exist during SSR, and its
// pdf.js worker must be configured in the same module that renders
// <Document>/<Page> (setting it elsewhere can be overwritten by module
// execution order) — so the actual viewer is a client-only dynamic import.
const PdfDocumentViewer = dynamic(() => import("./pdf-document-viewer"), {
  ssr: false,
  loading: () => <Skeleton className="h-[70vh] w-full" />,
});

interface PdfPreviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  fetchPdf: () => Promise<Blob>;
  onDownload: () => void;
  downloading?: boolean;
}

export function PdfPreviewDialog({
  open,
  onOpenChange,
  title,
  fetchPdf,
  onDownload,
  downloading = false,
}: PdfPreviewDialogProps) {
  const [blob, setBlob] = useState<Blob | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // fetchPdf is recreated each render by the caller — depending on it would
  // re-fetch on every parent re-render while the dialog stays open. Only
  // `open` should re-trigger the fetch.
  // biome-ignore lint/correctness/useExhaustiveDependencies: fetchPdf intentionally excluded, see comment above
  useEffect(() => {
    if (!open) return;
    setBlob(null);
    setError("");
    setLoading(true);
    let cancelled = false;
    fetchPdf()
      .then((b) => {
        if (!cancelled) setBlob(b);
      })
      .catch((err) => {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Could not load preview";
          setError(message);
          showErrorToast(message);
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
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>

        {loading && <Skeleton className="h-[70vh] w-full" />}

        {error && <p className="text-sm text-destructive">{error}</p>}

        {blob && !loading && <PdfDocumentViewer blob={blob} />}

        <div className="flex justify-end">
          <Button onClick={onDownload} disabled={downloading}>
            {downloading ? "Downloading…" : "Download PDF"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
