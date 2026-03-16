"use client";

import { Lock } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useSession } from "@/lib/auth-client";
import type { BOQResponse } from "@/lib/layout-types";

const SUPPORTED_CITIES = [
  "Generic",
  "Chennai",
  "Bangalore",
  "Hyderabad",
  "Pune",
  "Mumbai",
  "Delhi",
  "Trichy",
  "Coimbatore",
] as const;

type SupportedCity = (typeof SUPPORTED_CITIES)[number];

function formatINR(amount: number): string {
  if (amount >= 10_00_000) {
    return `₹${(amount / 10_00_000).toFixed(2)}L`;
  }
  if (amount >= 1_000) {
    return `₹${(amount / 1_000).toFixed(1)}K`;
  }
  return `₹${amount.toFixed(0)}`;
}

interface BOQViewerProps {
  projectId: string;
  layoutId: string;
  planTier?: string;
}

export function BOQViewer({ projectId, layoutId, planTier = "free" }: BOQViewerProps) {
  const { data: session } = useSession();
  const [boq, setBOQ] = useState<BOQResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [city, setCity] = useState<SupportedCity>("Generic");

  async function loadBOQ(selectedCity: SupportedCity = city) {
    if (!session) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/boq?layout_id=${layoutId}&fmt=json&city=${encodeURIComponent(selectedCity)}`,
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

  function handleCityChange(val: string) {
    const newCity = val as SupportedCity;
    setCity(newCity);
    if (boq) {
      // Refresh BOQ with new city if it was already loaded
      loadBOQ(newCity);
    }
  }

  async function downloadExcel() {
    if (!session) return;
    setDownloading(true);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/boq?layout_id=${layoutId}&fmt=excel&city=${encodeURIComponent(city)}`,
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
      <div className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">
          Generate a Bill of Quantities with approximate material takeoff and cost estimates for
          this layout.
        </p>

        {/* City selector */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-muted-foreground" htmlFor="city-select-pre">
            City / Region
          </label>
          <Select value={city} onValueChange={handleCityChange}>
            <SelectTrigger id="city-select-pre" className="w-48">
              <SelectValue placeholder="Select city" />
            </SelectTrigger>
            <SelectContent>
              {SUPPORTED_CITIES.map((c) => (
                <SelectItem key={c} value={c}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Material rates vary 20–30% across Indian cities. Select your city for accurate
            estimates.
          </p>
        </div>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => loadBOQ(city)}
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

  const diff = boq.cost_difference;
  const showComparison = boq.city !== "Generic" && diff !== null && diff !== 0;

  return (
    <div className="flex flex-col gap-4">
      {/* Header row: title + city selector + export */}
      <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-start sm:justify-between gap-3">
        <div className="flex flex-col gap-1">
          <p className="text-sm font-medium text-muted-foreground">
            Approximate quantities &amp; cost — Layout {boq.layout_id}
          </p>
          <p className="text-xs text-muted-foreground">{boq.rates_note}</p>

          {/* City comparison note */}
          {showComparison && diff !== null && (
            <p
              className={[
                "text-xs font-medium",
                diff > 0 ? "text-red-600 dark:text-red-400" : "text-green-600 dark:text-green-400",
              ].join(" ")}
            >
              {diff > 0 ? "▲" : "▼"} {formatINR(Math.abs(diff))} {diff > 0 ? "more" : "cheaper"}{" "}
              than Generic
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* City selector */}
          <Select value={city} onValueChange={handleCityChange}>
            <SelectTrigger className="h-9 w-full sm:h-8 sm:w-40 text-sm sm:text-xs">
              <SelectValue placeholder="Select city" />
            </SelectTrigger>
            <SelectContent>
              {SUPPORTED_CITIES.map((c) => (
                <SelectItem key={c} value={c} className="text-xs">
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {planTier === "pro" ? (
            <button
              type="button"
              onClick={downloadExcel}
              disabled={downloading}
              className="w-full sm:w-auto rounded-lg border border-border px-3 py-2 sm:py-1.5 text-sm sm:text-xs font-medium hover:bg-muted disabled:opacity-50 transition-colors min-h-[44px] sm:min-h-0"
            >
              {downloading ? "Downloading…" : "Export Excel"}
            </button>
          ) : (
            <Link
              href="/pricing"
              className="inline-flex w-full sm:w-auto items-center justify-center gap-1 rounded-lg border border-border px-3 py-2 sm:py-1.5 text-sm sm:text-xs font-medium hover:bg-muted transition-colors min-h-[44px] sm:min-h-0"
              title="Upgrade to Pro for Excel export"
            >
              <Lock className="h-3 w-3" />
              Export Excel
            </Link>
          )}
        </div>
      </div>

      {/* Total cost summary */}
      <div className="flex flex-wrap gap-4 rounded-lg border border-border bg-muted/30 px-4 py-3">
        <div className="flex flex-col">
          <span className="text-xs text-muted-foreground">Estimated Total</span>
          <span className="text-lg font-bold text-foreground">{formatINR(boq.total_cost)}</span>
        </div>
        {boq.city !== "Generic" && boq.generic_total_cost !== null && (
          <div className="flex flex-col">
            <span className="text-xs text-muted-foreground">Generic Estimate</span>
            <span className="text-base font-semibold text-muted-foreground">
              {formatINR(boq.generic_total_cost)}
            </span>
          </div>
        )}
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
              <th className="px-4 py-2.5 text-right font-semibold text-muted-foreground">
                Rate (₹)
              </th>
              <th className="px-4 py-2.5 text-right font-semibold text-muted-foreground">
                Amount (₹)
              </th>
            </tr>
          </thead>
          <tbody>
            {boq.items.map((item, idx) => (
              <tr key={item.item} className={idx % 2 === 0 ? "bg-background" : "bg-muted/20"}>
                <td className="px-4 py-2 text-muted-foreground">{item.item}</td>
                <td className="px-4 py-2">{item.description}</td>
                <td className="px-4 py-2 text-right font-mono">{item.quantity.toFixed(2)}</td>
                <td className="px-4 py-2 text-muted-foreground">{item.unit}</td>
                <td className="px-4 py-2 text-right font-mono text-muted-foreground">
                  {item.rate > 0 ? item.rate.toFixed(0) : "—"}
                </td>
                <td className="px-4 py-2 text-right font-mono">
                  {item.amount > 0 ? item.amount.toLocaleString("en-IN") : "—"}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t bg-muted/50 font-semibold">
              <td colSpan={5} className="px-4 py-2.5 text-right">
                Total Estimated Cost
              </td>
              <td className="px-4 py-2.5 text-right font-mono">
                {boq.total_cost.toLocaleString("en-IN")}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      <p className="text-xs text-muted-foreground">
        Quantities are approximate estimates based on NBC standard dimensions. Rates are 2026 market
        estimates and vary by contractor and material quality. Verify with site measurements and
        local market rates before procurement.
      </p>

      {loading && (
        <p className="text-xs text-muted-foreground animate-pulse">
          Recalculating with {city} rates…
        </p>
      )}
    </div>
  );
}
