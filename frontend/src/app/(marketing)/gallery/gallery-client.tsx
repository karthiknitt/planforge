"use client";

import { ArrowRight, LayoutGrid } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { FloorPlanSVG } from "@/components/floor-plan-svg";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { FloorPlanData, RoomData } from "@/lib/layout-types";

// ── Types ──────────────────────────────────────────────────────────────────────

export interface GalleryPlan {
  id: string;
  name: string;
  plot_width_m: number;
  plot_length_m: number;
  plot_width_ft: number;
  plot_length_ft: number;
  plot_area_sqft: number;
  num_bedrooms: number;
  bhk_label: string;
  num_toilets: number;
  parking: boolean;
  city: string;
  municipality: string | null;
  layout_id: string;
  layout_name: string;
  compliance_passed: boolean;
  score: number | null;
  estimated_cost_low: number;
  estimated_cost_high: number;
  rooms: RoomData[];
  columns: { x: number; y: number }[];
  floor: number;
  floor_type: string;
  needs_mech_ventilation: boolean;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatCrore(amount: number): string {
  const lakhs = amount / 100000;
  if (lakhs >= 100) {
    return `₹${(lakhs / 100).toFixed(1)}Cr`;
  }
  return `₹${Math.round(lakhs)}L`;
}

function plotSizeCategory(sqft: number): "small" | "medium" | "large" {
  if (sqft < 800) return "small";
  if (sqft <= 1500) return "medium";
  return "large";
}

function templateSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

// ── Filter bar ────────────────────────────────────────────────────────────────

type BhkFilter = "all" | "2bhk" | "3bhk" | "4bhk";
type SizeFilter = "all" | "small" | "medium" | "large";
type CityFilter = "all" | "Chennai" | "Bangalore" | "Generic";

interface FilterBarProps {
  bhk: BhkFilter;
  size: SizeFilter;
  city: CityFilter;
  onBhk: (v: BhkFilter) => void;
  onSize: (v: SizeFilter) => void;
  onCity: (v: CityFilter) => void;
}

function FilterBtn<T extends string>({
  active,
  value,
  label,
  onClick,
}: {
  active: boolean;
  value: T;
  label: string;
  onClick: (v: T) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onClick(value)}
      className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
        active
          ? "bg-primary text-primary-foreground border-primary shadow-sm"
          : "bg-card text-muted-foreground border-border/60 hover:border-border hover:text-foreground"
      }`}
    >
      {label}
    </button>
  );
}

function FilterBar({ bhk, size, city, onBhk, onSize, onCity }: FilterBarProps) {
  return (
    <div className="flex flex-wrap gap-4 items-center">
      {/* BHK */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider mr-1">
          BHK
        </span>
        {(["all", "2bhk", "3bhk", "4bhk"] as BhkFilter[]).map((v) => (
          <FilterBtn
            key={v}
            active={bhk === v}
            value={v}
            label={v === "all" ? "All" : v.toUpperCase()}
            onClick={onBhk}
          />
        ))}
      </div>

      <div className="h-5 w-px bg-border/60 hidden sm:block" />

      {/* Plot size */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider mr-1">
          Size
        </span>
        {(
          [
            { v: "all" as SizeFilter, label: "All" },
            { v: "small" as SizeFilter, label: "Small <800 sqft" },
            { v: "medium" as SizeFilter, label: "800–1500 sqft" },
            { v: "large" as SizeFilter, label: "Large >1500 sqft" },
          ] as { v: SizeFilter; label: string }[]
        ).map(({ v, label }) => (
          <FilterBtn key={v} active={size === v} value={v} label={label} onClick={onSize} />
        ))}
      </div>

      <div className="h-5 w-px bg-border/60 hidden sm:block" />

      {/* City */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider mr-1">
          City
        </span>
        {(
          [
            { v: "all" as CityFilter, label: "All" },
            { v: "Generic" as CityFilter, label: "Generic" },
            { v: "Chennai" as CityFilter, label: "Chennai" },
            { v: "Bangalore" as CityFilter, label: "Bangalore" },
          ] as { v: CityFilter; label: string }[]
        ).map(({ v, label }) => (
          <FilterBtn key={v} active={city === v} value={v} label={label} onClick={onCity} />
        ))}
      </div>
    </div>
  );
}

// ── Plan card ─────────────────────────────────────────────────────────────────

function PlanCard({ plan }: { plan: GalleryPlan }) {
  const floorPlanData: FloorPlanData = {
    floor: plan.floor,
    floor_type: plan.floor_type,
    rooms: plan.rooms,
    columns: plan.columns,
    needs_mech_ventilation: plan.needs_mech_ventilation,
  };

  const slug = templateSlug(plan.name);
  const costLow = formatCrore(plan.estimated_cost_low);
  const costHigh = formatCrore(plan.estimated_cost_high);

  const roomCount = plan.rooms.filter(
    (r) => !["staircase", "parking", "parking_4w", "parking_2w", "garage"].includes(r.type)
  ).length;

  return (
    <div className="feature-card group flex flex-col rounded-2xl border border-border/60 bg-card overflow-hidden hover:border-primary/30 transition-all duration-300">
      {/* SVG preview */}
      <div className="relative bg-muted/30 p-2 border-b border-border/40">
        <div className="w-full" style={{ maxWidth: 240, margin: "0 auto" }}>
          <FloorPlanSVG
            floorPlan={floorPlanData}
            plotWidth={plan.plot_width_m}
            plotLength={plan.plot_length_m}
            roadSide="S"
            showFurniture={false}
            showVastuZones={false}
          />
        </div>
      </div>

      {/* Card body */}
      <div className="flex flex-col flex-1 p-4 gap-3">
        {/* Title + BHK badge */}
        <div className="flex items-start justify-between gap-2">
          <h3
            className="text-sm font-bold text-foreground leading-tight"
            style={{ fontFamily: "var(--font-display)" }}
          >
            {plan.name}
          </h3>
          <Badge className="flex-shrink-0 bg-primary/10 text-primary border-primary/25 text-xs px-2 py-0.5">
            {plan.bhk_label}
          </Badge>
        </div>

        {/* Dims + area */}
        <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
          <span>
            {plan.plot_width_ft}×{plan.plot_length_ft} ft
          </span>
          <span className="text-border">·</span>
          <span>{plan.plot_area_sqft.toLocaleString("en-IN")} sqft</span>
          {plan.city !== "Generic" && (
            <>
              <span className="text-border">·</span>
              <span>{plan.city}</span>
            </>
          )}
        </div>

        {/* Room summary */}
        <div className="flex flex-wrap gap-1.5 text-xs">
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-muted/60 text-muted-foreground">
            <LayoutGrid className="h-3 w-3" />
            {roomCount} rooms
          </span>
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-muted/60 text-muted-foreground">
            {plan.num_toilets} bath
          </span>
          {plan.parking && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-muted/60 text-muted-foreground">
              Parking
            </span>
          )}
          {plan.compliance_passed && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-green-500/10 text-green-600 dark:text-green-400">
              NBC compliant
            </span>
          )}
        </div>

        {/* Cost estimate */}
        <p className="text-xs text-muted-foreground">
          Est.{" "}
          <span className="font-semibold text-foreground">
            {costLow}–{costHigh}
          </span>
        </p>

        {/* CTA */}
        <div className="mt-auto pt-1">
          <Link href={`/sign-up?template=${slug}`}>
            <Button
              size="sm"
              className="w-full bg-primary/10 hover:bg-primary text-primary hover:text-primary-foreground border border-primary/25 hover:border-primary font-semibold text-xs h-8 transition-all"
            >
              Customize this plan
              <ArrowRight className="ml-1.5 h-3 w-3" />
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}

// ── Gallery client shell ──────────────────────────────────────────────────────

export function GalleryClient({ plans }: { plans: GalleryPlan[] }) {
  const [bhk, setBhk] = useState<BhkFilter>("all");
  const [size, setSize] = useState<SizeFilter>("all");
  const [city, setCity] = useState<CityFilter>("all");

  const filtered = plans.filter((p) => {
    if (bhk !== "all" && p.bhk_label.toLowerCase() !== bhk) return false;
    if (size !== "all" && plotSizeCategory(p.plot_area_sqft) !== size) return false;
    if (city !== "all" && p.city !== city) return false;
    return true;
  });

  return (
    <div>
      {/* Filter bar */}
      <div className="mb-8">
        <FilterBar
          bhk={bhk}
          size={size}
          city={city}
          onBhk={setBhk}
          onSize={setSize}
          onCity={setCity}
        />
      </div>

      {/* Result count */}
      <p className="text-sm text-muted-foreground mb-6">
        Showing <span className="font-semibold text-foreground">{filtered.length}</span> of{" "}
        {plans.length} templates
      </p>

      {/* Grid */}
      {filtered.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {filtered.map((plan) => (
            <PlanCard key={plan.id} plan={plan} />
          ))}
        </div>
      ) : (
        <div className="text-center py-16">
          <p className="text-muted-foreground text-sm">
            No templates match the selected filters.{" "}
            <button
              type="button"
              className="text-primary underline underline-offset-4 hover:no-underline"
              onClick={() => {
                setBhk("all");
                setSize("all");
                setCity("all");
              }}
            >
              Clear filters
            </button>
          </p>
        </div>
      )}
    </div>
  );
}
