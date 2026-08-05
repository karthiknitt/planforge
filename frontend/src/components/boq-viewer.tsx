"use client";

import { Lock } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useSession } from "@/lib/auth-client";
import { boqBasisLabel, shouldShowPreliminaryBanner } from "@/lib/boq-provenance";
import type { BOQResponse } from "@/lib/layout-types";
import { showErrorToast, showToast } from "@/lib/toast";

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
  if (amount >= 1_00_00_000) {
    return `₹${(amount / 1_00_00_000).toFixed(2)}Cr`;
  }
  if (amount >= 1_00_000) {
    return `₹${(amount / 1_00_000).toFixed(2)}L`;
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
  // BOQ needs sized beams/columns/footings from a structural design to
  // produce real quantities — gated hard rather than falling back to an
  // architectural-only estimate (see structural-boq-gating-and-hints plan).
  structuralDesigned: boolean;
  onRunStructuralDesign: () => void;
}

export function BOQViewer({
  projectId,
  layoutId,
  planTier = "free",
  structuralDesigned,
  onRunStructuralDesign,
}: BOQViewerProps) {
  const { data: session } = useSession();
  const [boq, setBOQ] = useState<BOQResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [city, setCity] = useState<SupportedCity>("Generic");

  // Reset the loaded BOQ when the viewed layout changes — the component
  // stays mounted across layout switches, so Layout A's table (and its
  // provenance badges/totals) lingered under Layout B's header while the
  // Excel export already targeted B. Mirrors StructuralViewer's guard.
  // biome-ignore lint/correctness/useExhaustiveDependencies: layoutId is an intentional reset trigger, not read in the body
  useEffect(() => {
    setBOQ(null);
    setError("");
  }, [layoutId]);

  async function loadBOQ(selectedCity: SupportedCity = city) {
    if (!session) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch(
        `/api/backend/projects/${projectId}/boq?layout_id=${layoutId}&fmt=json&city=${encodeURIComponent(selectedCity)}`
      );
      if (!res.ok) throw new Error("Failed to load BOQ");
      setBOQ(await res.json());
    } catch (e) {
      const message = e instanceof Error ? e.message : "Something went wrong";
      setError(message);
      showErrorToast(message);
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
        `/api/backend/projects/${projectId}/boq?layout_id=${layoutId}&fmt=excel&city=${encodeURIComponent(city)}`
      );
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `planforge-boq-layout-${layoutId}.xlsx`;
        a.click();
        URL.revokeObjectURL(url);
        showToast("success", "BOQ Excel downloaded");
      } else {
        try {
          const errData = await res.json();
          const message = errData.detail || "Failed to download Excel file";
          setError(message);
          showErrorToast(message);
        } catch {
          const message = `Download failed: ${res.statusText}`;
          setError(message);
          showErrorToast(message);
        }
      }
    } catch (e) {
      const message = e instanceof Error ? e.message : "Download failed";
      setError(message);
      showErrorToast(message);
    } finally {
      setDownloading(false);
    }
  }

  if (!structuralDesigned) {
    return (
      <div className="flex flex-col gap-3 rounded-lg border border-border bg-muted/20 p-4 text-sm">
        <p className="font-medium">Run structural design first</p>
        <p className="text-muted-foreground">
          The Bill of Quantities needs sized beams, columns and footings from the structural design
          to produce accurate quantities and costs. Run structural design, then come back to this
          tab.
        </p>
        <button
          type="button"
          onClick={onRunStructuralDesign}
          className="w-fit rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-muted transition-colors"
        >
          Go to Structural tab
        </button>
      </div>
    );
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
          <Select
            id="city-select-pre"
            value={city}
            onChange={(e) => handleCityChange(e.target.value)}
            className="w-48"
          >
            {SUPPORTED_CITIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
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
  const showPreliminaryBanner = shouldShowPreliminaryBanner(boq);

  return (
    <div className="flex flex-col gap-4">
      {showPreliminaryBanner && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs font-semibold text-amber-700 dark:text-amber-400">
          PRELIMINARY ESTIMATE — based on architectural quantities only. Run structural design for
          IS-code-backed member sizing.
        </div>
      )}

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
          <Select
            value={city}
            onChange={(e) => handleCityChange(e.target.value)}
            className="h-9 w-full sm:h-8 sm:w-40 text-sm sm:text-xs"
          >
            {SUPPORTED_CITIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
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

      <div className="rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/50">
              <TableHead className="text-muted-foreground">S.No</TableHead>
              <TableHead className="text-muted-foreground">Item Description</TableHead>
              <TableHead className="text-muted-foreground">Basis</TableHead>
              <TableHead className="text-right text-muted-foreground">Quantity</TableHead>
              <TableHead className="text-muted-foreground">Unit</TableHead>
              <TableHead className="text-right text-muted-foreground">Rate (₹)</TableHead>
              <TableHead className="text-right text-muted-foreground">Amount (₹)</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {boq.items.map((item, idx) => (
              <TableRow key={item.item} className={idx % 2 === 0 ? "bg-background" : "bg-muted/20"}>
                <TableCell className="text-muted-foreground">{item.item}</TableCell>
                <TableCell className="whitespace-normal">{item.description}</TableCell>
                <TableCell>
                  <Badge
                    variant={item.basis === "designed" ? "default" : "outline"}
                    className="text-[10px]"
                  >
                    {boqBasisLabel(item.basis)}
                  </Badge>
                </TableCell>
                <TableCell className="text-right font-mono">{item.quantity.toFixed(2)}</TableCell>
                <TableCell className="text-muted-foreground">{item.unit}</TableCell>
                <TableCell className="text-right font-mono text-muted-foreground">
                  {item.rate > 0 ? item.rate.toFixed(0) : "—"}
                </TableCell>
                <TableCell className="text-right font-mono">
                  {item.amount > 0 ? item.amount.toLocaleString("en-IN") : "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
          <TableFooter>
            <TableRow className="font-semibold">
              <TableCell colSpan={6} className="text-right">
                Total Estimated Cost
              </TableCell>
              <TableCell className="text-right font-mono">
                {boq.total_cost.toLocaleString("en-IN")}
              </TableCell>
            </TableRow>
          </TableFooter>
        </Table>
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
