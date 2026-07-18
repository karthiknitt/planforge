"use client";

import { useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

// Must be set in the same client-only module that renders <Document> — pdf.js
// resolves the worker relative to this module's own bundle location.
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

export default function PdfDocumentViewer({ blob }: { blob: Blob }) {
  const [numPages, setNumPages] = useState(0);
  const [pageNumber, setPageNumber] = useState(1);
  const [pageError, setPageError] = useState(false);
  const [pageLoadError, setPageLoadError] = useState<string | null>(null);

  if (pageError) {
    return (
      <p className="text-sm text-muted-foreground">
        Preview unavailable for this drawing — download the PDF instead.
      </p>
    );
  }

  return (
    <div className="flex flex-col items-center gap-3">
      <Document
        file={blob}
        onLoadSuccess={({ numPages: n }) => {
          setNumPages(n);
          setPageNumber(1);
        }}
        onLoadError={() => setPageError(true)}
        loading={<Skeleton className="h-[70vh] w-full" />}
      >
        <Page
          pageNumber={pageNumber}
          width={640}
          onLoadSuccess={() => setPageLoadError(null)}
          onLoadError={(err) => {
            // react-pdf's own warning() is a no-op in production builds, so
            // without this the failure is otherwise completely silent.
            console.error(`PDF page ${pageNumber} failed to load:`, err);
            setPageLoadError(err.message);
          }}
          onRenderError={(err) => {
            console.error(`PDF page ${pageNumber} failed to render:`, err);
            setPageLoadError(err.message);
          }}
        />
      </Document>

      {pageLoadError && (
        <p className="text-sm text-destructive">
          Couldn't load page {pageNumber}: {pageLoadError}
        </p>
      )}

      {numPages > 1 && (
        <div className="flex items-center gap-3 text-sm">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPageNumber((p) => Math.max(1, p - 1))}
            disabled={pageNumber <= 1}
          >
            Previous
          </Button>
          <span className="text-muted-foreground">
            Page {pageNumber} of {numPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPageNumber((p) => Math.min(numPages, p + 1))}
            disabled={pageNumber >= numPages}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
