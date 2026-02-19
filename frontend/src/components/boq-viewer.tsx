"use client";

import { useState } from "react";
import { useSession } from "@/lib/auth-client";
import type { BOQResponse } from "@/lib/layout-types";

interface BOQViewerProps {
  projectId: string;
  layoutId: string;
}

export function BOQViewer({ projectId, layoutId }: BOQViewerProps) {
  const { data: session } = useSession();
  const [boq, setBOQ] = useState<BOQResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);

  async function loadBOQ() {
    if (!session) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/boq?layout_id=${layoutId}&fmt=json`,
        { headers: { "X-User-Id": session.user.id } }
      );
      if (!res.ok) throw new Error("Failed to load BOQ");
      setBOQ(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function downloadExcel() {
    if (!session) return;
    setDownloading(true);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/boq?layout_id=${layoutId}&fmt=excel`,
        { headers: { "X-User-Id": session.user.id } }
      );
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `planforge-boq-layout-${layoutId}.xlsx`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } finally {
      setDownloading(false);
    }
  }

  if (!boq) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">
          Generate a Bill of Quantities with approximate material takeoff for this layout.
        </p>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={loadBOQ}
            disabled={loading || !session}
            className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-muted disabled:opacity-50 transition-colors"
          >
            {loading ? "Loading…" : "Generate BOQ"}
          </button>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-muted-foreground">
          Approximate quantities for Layout {boq.layout_id}
        </p>
        <button
          type="button"
          onClick={downloadExcel}
          disabled={downloading}
          className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted disabled:opacity-50 transition-colors"
        >
          {downloading ? "Downloading…" : "Export Excel"}
        </button>
      </div>

      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50">
              <th className="px-4 py-2.5 text-left font-semibold text-muted-foreground">S.No</th>
              <th className="px-4 py-2.5 text-left font-semibold text-muted-foreground">
                Item Description
              </th>
              <th className="px-4 py-2.5 text-right font-semibold text-muted-foreground">
                Quantity
              </th>
              <th className="px-4 py-2.5 text-left font-semibold text-muted-foreground">Unit</th>
            </tr>
          </thead>
          <tbody>
            {boq.items.map((item, idx) => (
              <tr key={item.item} className={idx % 2 === 0 ? "bg-background" : "bg-muted/20"}>
                <td className="px-4 py-2 text-muted-foreground">{item.item}</td>
                <td className="px-4 py-2">{item.description}</td>
                <td className="px-4 py-2 text-right font-mono">{item.quantity.toFixed(2)}</td>
                <td className="px-4 py-2 text-muted-foreground">{item.unit}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-muted-foreground">
        Quantities are approximate estimates based on NBC standard dimensions. Verify with site
        measurements before procurement. Add current market rates in the exported Excel file.
      </p>
    </div>
  );
}
