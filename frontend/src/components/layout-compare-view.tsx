"use client";

import { AlertTriangle, Check, X } from "lucide-react";
import { useState } from "react";

import { FloorPlanSVG } from "@/components/floor-plan-svg";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { FloorPlanData, LayoutData } from "@/lib/layout-types";
import { type Locale, useLocale } from "@/lib/locale-context";

// ── Props ─────────────────────────────────────────────────────────────────────

interface LayoutCompareViewProps {
  layouts: LayoutData[];
  plotWidth: number;
  plotLength: number;
  roadSide: string;
  plotShape?: string;
  plotFrontWidth?: number;
  plotRearWidth?: number;
  plotCorners?: [number, number][];
  cutoutCorner?: string;
  cutoutWidth?: number;
  cutoutHeight?: number;
}

// ── Floor selector helpers ────────────────────────────────────────────────────

interface FloorEntry {
  label: string;
  key: string;
  plan: FloorPlanData;
}

function getAvailableFloors(layout: LayoutData): FloorEntry[] {
  const floors: FloorEntry[] = [];
  if (layout.basement_floor) {
    floors.push({ label: "Basement", key: "basement", plan: layout.basement_floor });
  }
  floors.push({
    label: layout.ground_floor.floor_type === "stilt" ? "Stilt Floor" : "Ground Floor",
    key: "ground",
    plan: layout.ground_floor,
  });
  floors.push({ label: "First Floor", key: "first", plan: layout.first_floor });
  if (layout.second_floor) {
    floors.push({ label: "Second Floor", key: "second", plan: layout.second_floor });
  }
  return floors;
}

// ── Score colour helper ───────────────────────────────────────────────────────

function scoreColour(score: number): string {
  if (score >= 75) return "bg-success/15 text-success border-success/40";
  if (score >= 55) return "bg-warning/15 text-warning border-warning/40";
  return "bg-destructive/15 text-destructive border-destructive/40";
}

// ── Total area calculation ────────────────────────────────────────────────────

function totalArea(layout: LayoutData): number {
  const floors = [
    layout.basement_floor,
    layout.ground_floor,
    layout.first_floor,
    layout.second_floor,
  ];
  return floors
    .filter((f): f is FloorPlanData => f !== null && f !== undefined)
    .flatMap((f) => f.rooms)
    .reduce((sum, r) => sum + r.area, 0);
}

function bedroomCount(layout: LayoutData): number {
  const all = [layout.basement_floor, layout.ground_floor, layout.first_floor, layout.second_floor]
    .filter((f): f is FloorPlanData => f !== null && f !== undefined)
    .flatMap((f) => f.rooms);
  return all.filter((r) => r.type === "bedroom" || r.type === "master_bedroom").length;
}

// ── Single-column panel ───────────────────────────────────────────────────────

interface PanelProps {
  layouts: LayoutData[];
  selectedId: string;
  onSelect: (id: string) => void;
  floorKey: string;
  onFloorChange: (key: string) => void;
  plotWidth: number;
  plotLength: number;
  roadSide: string;
  plotShape?: string;
  plotFrontWidth?: number;
  plotRearWidth?: number;
  plotCorners?: [number, number][];
  cutoutCorner?: string;
  cutoutWidth?: number;
  cutoutHeight?: number;
  locale?: Locale;
}

function LayoutPanel({
  layouts,
  selectedId,
  onSelect,
  floorKey,
  onFloorChange,
  plotWidth,
  plotLength,
  roadSide,
  plotShape,
  plotFrontWidth,
  plotRearWidth,
  plotCorners,
  cutoutCorner,
  cutoutWidth,
  cutoutHeight,
  locale = "en",
}: PanelProps) {
  const layout = layouts.find((l) => l.id === selectedId) ?? layouts[0];
  const floors = getAvailableFloors(layout);
  const currentFloor = floors.find((f) => f.key === floorKey) ?? floors[1] ?? floors[0];

  return (
    <div className="flex flex-col gap-3 min-w-0">
      {/* Layout picker */}
      <Select value={selectedId} onChange={(e) => onSelect(e.target.value)} className="w-full">
        {layouts.map((l) => (
          <option key={l.id} value={l.id}>
            Layout {l.id} — {l.name}
            {l.score ? ` · ${l.score.total.toFixed(0)}/100` : ""}
          </option>
        ))}
      </Select>

      {/* Score + compliance badges */}
      <div className="flex flex-wrap gap-2">
        {layout.score && (
          <Badge
            variant="outline"
            className={`rounded-md border px-2 py-0.5 text-xs font-semibold ${scoreColour(layout.score.total)}`}
          >
            Score {layout.score.total.toFixed(0)}/100
          </Badge>
        )}
        <Badge
          variant="outline"
          className={
            layout.compliance.passed
              ? "border-success/40 bg-success/10 text-success"
              : "border-destructive/40 bg-destructive/10 text-destructive"
          }
        >
          <div className="flex items-center gap-1.5">
            {layout.compliance.passed ? (
              <>
                <Check className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span>Compliant</span>
              </>
            ) : (
              <>
                <X className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span>
                  {layout.compliance.violations.length} violation
                  {layout.compliance.violations.length !== 1 ? "s" : ""}
                </span>
              </>
            )}
          </div>
        </Badge>
        {layout.compliance.warnings.length > 0 && (
          <Badge variant="outline" className="border-warning/40 bg-warning/10 text-warning">
            <div className="flex items-center gap-1.5">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              <span>
                {layout.compliance.warnings.length} warning
                {layout.compliance.warnings.length !== 1 ? "s" : ""}
              </span>
            </div>
          </Badge>
        )}
      </div>

      {/* Floor selector */}
      <Tabs value={currentFloor.key} onValueChange={onFloorChange} className="w-fit">
        <TabsList variant="line">
          {floors.map((f) => (
            <TabsTrigger key={f.key} value={f.key} className="flex-none px-3 py-1">
              {f.label}
              {f.plan.needs_mech_ventilation && (
                <AlertTriangle className="ml-1 h-3 w-3 text-warning shrink-0" aria-hidden="true" />
              )}
              {f.plan.needs_mech_ventilation && (
                <span className="sr-only">Mechanical ventilation required</span>
              )}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {/* Floor plan SVG */}
      <FloorPlanSVG
        floorPlan={currentFloor.plan}
        plotWidth={plotWidth}
        plotLength={plotLength}
        roadSide={roadSide}
        className="w-full rounded-xl border"
        plotShape={plotShape}
        plotFrontWidth={plotFrontWidth}
        plotRearWidth={plotRearWidth}
        plotCorners={plotCorners}
        cutoutCorner={cutoutCorner}
        cutoutWidth={cutoutWidth}
        cutoutHeight={cutoutHeight}
        locale={locale}
      />
    </div>
  );
}

// ── Comparison summary table ──────────────────────────────────────────────────

interface SummaryTableProps {
  leftLayout: LayoutData;
  rightLayout: LayoutData;
}

function ComparisonSummaryTable({ leftLayout, rightLayout }: SummaryTableProps) {
  const leftArea = totalArea(leftLayout);
  const rightArea = totalArea(rightLayout);
  const leftBeds = bedroomCount(leftLayout);
  const rightBeds = bedroomCount(rightLayout);

  const rows: {
    metric: string;
    left: React.ReactNode;
    right: React.ReactNode;
  }[] = [
    {
      metric: "Total built-up area",
      left: `${leftArea.toFixed(1)} m²`,
      right: `${rightArea.toFixed(1)} m²`,
    },
    {
      metric: "Bedrooms",
      left: String(leftBeds),
      right: String(rightBeds),
    },
    {
      metric: "Compliance",
      left: leftLayout.compliance.passed ? (
        <span className="text-success font-medium flex items-center gap-1.5">
          <Check className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>Pass</span>
        </span>
      ) : (
        <span className="text-destructive font-medium flex items-center gap-1.5">
          <X className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            {leftLayout.compliance.violations.length} violation
            {leftLayout.compliance.violations.length !== 1 ? "s" : ""}
          </span>
        </span>
      ),
      right: rightLayout.compliance.passed ? (
        <span className="text-success font-medium flex items-center gap-1.5">
          <Check className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>Pass</span>
        </span>
      ) : (
        <span className="text-destructive font-medium flex items-center gap-1.5">
          <X className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            {rightLayout.compliance.violations.length} violation
            {rightLayout.compliance.violations.length !== 1 ? "s" : ""}
          </span>
        </span>
      ),
    },
    {
      metric: "Warnings",
      left:
        leftLayout.compliance.warnings.length === 0 ? (
          <span className="text-muted-foreground">None</span>
        ) : (
          <span className="text-warning flex items-center gap-1.5">
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{leftLayout.compliance.warnings.length}</span>
          </span>
        ),
      right:
        rightLayout.compliance.warnings.length === 0 ? (
          <span className="text-muted-foreground">None</span>
        ) : (
          <span className="text-warning flex items-center gap-1.5">
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{rightLayout.compliance.warnings.length}</span>
          </span>
        ),
    },
    {
      metric: "Score",
      left: leftLayout.score ? (
        <span className={`font-semibold ${scoreColour(leftLayout.score.total)}`}>
          {leftLayout.score.total.toFixed(0)}/100
        </span>
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
      right: rightLayout.score ? (
        <span className={`font-semibold ${scoreColour(rightLayout.score.total)}`}>
          {rightLayout.score.total.toFixed(0)}/100
        </span>
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
    },
    {
      metric: "Natural light",
      left: leftLayout.score ? (
        `${leftLayout.score.natural_light.toFixed(0)}`
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
      right: rightLayout.score ? (
        `${rightLayout.score.natural_light.toFixed(0)}`
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
    },
    {
      metric: "Adjacency",
      left: leftLayout.score ? (
        `${leftLayout.score.adjacency.toFixed(0)}`
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
      right: rightLayout.score ? (
        `${rightLayout.score.adjacency.toFixed(0)}`
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
    },
    {
      metric: "Vastu",
      left: leftLayout.score ? (
        `${leftLayout.score.vastu.toFixed(0)}`
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
      right: rightLayout.score ? (
        `${rightLayout.score.vastu.toFixed(0)}`
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
    },
  ];

  return (
    <div className="rounded-xl border border-border overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[200px] text-muted-foreground">Metric</TableHead>
            <TableHead>
              Layout {leftLayout.id} — {leftLayout.name}
            </TableHead>
            <TableHead>
              Layout {rightLayout.id} — {rightLayout.name}
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.metric}>
              <TableCell className="font-medium text-muted-foreground">{row.metric}</TableCell>
              <TableCell>{row.left}</TableCell>
              <TableCell>{row.right}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function LayoutCompareView({
  layouts,
  plotWidth,
  plotLength,
  roadSide,
  plotShape,
  plotFrontWidth,
  plotRearWidth,
  plotCorners,
  cutoutCorner,
  cutoutWidth,
  cutoutHeight,
}: LayoutCompareViewProps) {
  // Default: first two layouts
  const { locale } = useLocale();
  const [leftId, setLeftId] = useState<string>(layouts[0]?.id ?? "");
  const [rightId, setRightId] = useState<string>(layouts[1]?.id ?? layouts[0]?.id ?? "");
  const [leftFloor, setLeftFloor] = useState<string>("ground");
  const [rightFloor, setRightFloor] = useState<string>("ground");

  if (layouts.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border p-12 text-center text-muted-foreground">
        <p className="font-medium">No layouts available to compare</p>
      </div>
    );
  }

  const leftLayout = layouts.find((l) => l.id === leftId) ?? layouts[0];
  const rightLayout = layouts.find((l) => l.id === rightId) ?? layouts[layouts.length > 1 ? 1 : 0];

  return (
    <div className="flex flex-col gap-6">
      {/* Side-by-side panels */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <LayoutPanel
          layouts={layouts}
          selectedId={leftId}
          onSelect={(id) => {
            setLeftId(id);
            setLeftFloor("ground");
          }}
          floorKey={leftFloor}
          onFloorChange={setLeftFloor}
          plotWidth={plotWidth}
          plotLength={plotLength}
          roadSide={roadSide}
          plotShape={plotShape}
          plotFrontWidth={plotFrontWidth}
          plotRearWidth={plotRearWidth}
          plotCorners={plotCorners}
          cutoutCorner={cutoutCorner}
          cutoutWidth={cutoutWidth}
          cutoutHeight={cutoutHeight}
          locale={locale}
        />
        <LayoutPanel
          layouts={layouts}
          selectedId={rightId}
          onSelect={(id) => {
            setRightId(id);
            setRightFloor("ground");
          }}
          floorKey={rightFloor}
          onFloorChange={setRightFloor}
          plotWidth={plotWidth}
          plotLength={plotLength}
          roadSide={roadSide}
          plotShape={plotShape}
          plotFrontWidth={plotFrontWidth}
          plotRearWidth={plotRearWidth}
          plotCorners={plotCorners}
          cutoutCorner={cutoutCorner}
          cutoutWidth={cutoutWidth}
          cutoutHeight={cutoutHeight}
          locale={locale}
        />
      </div>

      {/* Summary comparison table */}
      <div className="flex flex-col gap-2">
        <p className="text-sm font-semibold text-foreground">Summary Comparison</p>
        <ComparisonSummaryTable leftLayout={leftLayout} rightLayout={rightLayout} />
      </div>
    </div>
  );
}
