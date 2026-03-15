"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { useSession } from "@/lib/auth-client";
import { CITIES, MUNICIPALITIES } from "@/lib/layout-types";

const DIRECTIONS = ["N", "S", "E", "W"] as const;
const DIRECTION_LABELS: Record<string, string> = { N: "North", S: "South", E: "East", W: "West" };
const OPPOSITE: Record<string, string> = { N: "S", S: "N", E: "W", W: "E" };

function feetToMetres(feet: string): number {
  return Math.round(parseFloat(feet) * 0.3048 * 1000) / 1000;
}

function metresToFeet(metres: string | number): string {
  return (Math.round((parseFloat(String(metres)) / 0.3048) * 10) / 10).toString();
}

interface ProjectData {
  id: string;
  name: string;
  plotLength: string;
  plotWidth: string;
  setbackFront: string;
  setbackRear: string;
  setbackLeft: string;
  setbackRight: string;
  roadSide: string;
  numBedrooms: number;
  toilets: number;
  parking: boolean;
  city?: string;
  municipality?: string | null;
  roadWidthM?: number;
  hasPooja?: boolean;
  hasStudy?: boolean;
  hasBalcony?: boolean;
  plotShape?: string;
  plotFrontWidth?: string | null;
  plotRearWidth?: string | null;
  plotSideOffset?: string | null;
  plotCorners?: string | null;
  numFloors?: number;
  hasStilt?: boolean;
  hasBasement?: boolean;
  vastuEnabled?: boolean;
}

/* ── Live plot compass ─────────────────────────────────────────────────────── */
function PlotCompass({ roadSide }: { roadSide: string }) {
  const arrowAngles: Record<string, number> = { N: 0, E: 90, S: 180, W: 270 };
  const roadLines: Record<string, { x1: number; y1: number; x2: number; y2: number }> = {
    N: { x1: 20, y1: 20, x2: 100, y2: 20 },
    S: { x1: 20, y1: 100, x2: 100, y2: 100 },
    E: { x1: 100, y1: 20, x2: 100, y2: 100 },
    W: { x1: 20, y1: 20, x2: 20, y2: 100 },
  };
  const roadLabel: Record<string, { x: number; y: number }> = {
    N: { x: 60, y: 13 },
    S: { x: 60, y: 113 },
    E: { x: 113, y: 62 },
    W: { x: 6, y: 62 },
  };

  const road = roadLines[roadSide] ?? roadLines.S;
  const label = roadLabel[roadSide] ?? roadLabel.S;
  const northAngle = arrowAngles[OPPOSITE[roadSide]] ?? 0;

  return (
    <svg viewBox="0 0 120 120" className="w-full h-full" aria-label="Plot orientation compass">
      <rect
        x="20"
        y="20"
        width="80"
        height="80"
        fill="transparent"
        stroke="currentColor"
        className="text-border"
        strokeWidth="1.5"
        strokeDasharray="4 2"
      />
      <line {...road} stroke="#f97316" strokeWidth="5" strokeLinecap="round" />
      <text
        x={label.x}
        y={label.y}
        textAnchor="middle"
        dominantBaseline="middle"
        fontSize="7"
        fontWeight="700"
        fill="#f97316"
        fontFamily="sans-serif"
      >
        ROAD
      </text>
      <g transform={`translate(60,60) rotate(${northAngle})`}>
        <polygon points="0,-16 -4,0 0,-4 4,0" fill="currentColor" className="text-foreground" />
        <polygon points="0,16 -4,0 0,4 4,0" fill="#CBD5E1" />
      </g>
      {(() => {
        const angle = (northAngle * Math.PI) / 180;
        const nx = 60 + Math.sin(angle) * -24;
        const ny = 60 + Math.cos(angle) * -24;
        return (
          <text
            x={nx}
            y={ny}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize="8"
            fontWeight="700"
            fill="currentColor"
            className="text-foreground"
            fontFamily="sans-serif"
          >
            N
          </text>
        );
      })()}
    </svg>
  );
}

/* ── Section header ────────────────────────────────────────────────────────── */
function Section({ num, title }: { num: string; title: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
        {num}
      </span>
      <span className="text-sm font-semibold text-foreground tracking-wide uppercase">{title}</span>
      <Separator className="flex-1" />
    </div>
  );
}

/* ── Edit form ─────────────────────────────────────────────────────────────── */
export function EditProjectForm({ project }: { project: ProjectData }) {
  const router = useRouter();
  const { data: session } = useSession();

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const _initCorners = (): { x: string; y: string }[] => {
    if (project.plotCorners) {
      try {
        const parsed = JSON.parse(project.plotCorners) as [number, number][];
        return parsed.map(([x, y]) => ({ x: String(x), y: String(y) }));
      } catch {
        /* fall through */
      }
    }
    return [
      { x: "0", y: "0" },
      { x: "", y: "0" },
      { x: "", y: "" },
      { x: "0", y: "" },
    ];
  };
  const [quadCorners, setQuadCorners] = useState(_initCorners);

  function setQuadCorner(idx: number, field: "x" | "y", value: string) {
    setQuadCorners((prev) => prev.map((c, i) => (i === idx ? { ...c, [field]: value } : c)));
  }

  function isConvex(pts: [number, number][]): boolean {
    const n = pts.length;
    let sign = 0;
    for (let i = 0; i < n; i++) {
      const [x1, y1] = pts[i];
      const [x2, y2] = pts[(i + 1) % n];
      const [x3, y3] = pts[(i + 2) % n];
      const cross = (x2 - x1) * (y3 - y2) - (y2 - y1) * (x3 - x2);
      if (cross !== 0) {
        const s = cross > 0 ? 1 : -1;
        if (sign === 0) sign = s;
        else if (s !== sign) return false;
      }
    }
    return true;
  }

  function polygonArea(pts: [number, number][]): number {
    let area = 0;
    for (let i = 0; i < pts.length; i++) {
      const [x1, y1] = pts[i];
      const [x2, y2] = pts[(i + 1) % pts.length];
      area += x1 * y2 - x2 * y1;
    }
    return Math.abs(area) / 2;
  }

  const [form, setForm] = useState({
    name: project.name,
    plot_shape: project.plotShape ?? "rectangular",
    plot_length: metresToFeet(project.plotLength),
    plot_width: metresToFeet(project.plotWidth),
    plot_front_width: project.plotFrontWidth ? metresToFeet(project.plotFrontWidth) : "",
    plot_rear_width: project.plotRearWidth ? metresToFeet(project.plotRearWidth) : "",
    setback_front: metresToFeet(project.setbackFront),
    setback_rear: metresToFeet(project.setbackRear),
    setback_left: metresToFeet(project.setbackLeft),
    setback_right: metresToFeet(project.setbackRight),
    road_side: project.roadSide,
    num_bedrooms: String(project.numBedrooms),
    toilets: String(project.toilets),
    parking: project.parking,
    city: project.city ?? "other",
    municipality: project.municipality ?? "",
    municipality_other: "",
    road_width_m: String(Math.round((project.roadWidthM ?? 9) / 0.3048)),
    has_pooja: project.hasPooja ?? false,
    has_study: project.hasStudy ?? false,
    has_balcony: project.hasBalcony ?? false,
    num_floors: String(project.numFloors ?? 1),
    has_stilt: project.hasStilt ?? false,
    has_basement: project.hasBasement ?? false,
    vastu_enabled: project.vastuEnabled ?? false,
  });

  function set(field: string, value: string | boolean) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/projects/${project.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": session!.user.id,
        },
        body: JSON.stringify(
          (() => {
            const base: Record<string, unknown> = {
              name: form.name,
              plot_shape: form.plot_shape,
              plot_side_offset: 0,
            };
            if (form.plot_shape === "quadrilateral") {
              const pts = quadCorners.map(
                (c) => [parseFloat(c.x) || 0, parseFloat(c.y) || 0] as [number, number]
              );
              if (!isConvex(pts))
                throw new Error("Quadrilateral corners must form a convex polygon.");
              if (polygonArea(pts) < 30) throw new Error("Plot area must be at least 30 sqm.");
              const xs = pts.map(([x]) => x);
              const ys = pts.map(([, y]) => y);
              base.plot_corners = pts;
              base.plot_length = Math.max(...ys);
              base.plot_width = Math.max(...xs);
              base.plot_front_width = null;
              base.plot_rear_width = null;
            } else {
              base.plot_length = feetToMetres(form.plot_length);
              base.plot_width =
                form.plot_shape === "trapezoid"
                  ? feetToMetres(
                      String(
                        Math.max(
                          parseFloat(form.plot_front_width) || 0,
                          parseFloat(form.plot_rear_width) || 0
                        )
                      )
                    )
                  : feetToMetres(form.plot_width);
              base.plot_front_width =
                form.plot_shape === "trapezoid" ? feetToMetres(form.plot_front_width) : null;
              base.plot_rear_width =
                form.plot_shape === "trapezoid" ? feetToMetres(form.plot_rear_width) : null;
            }
            const resolvedMunicipality =
              form.municipality === "Other"
                ? form.municipality_other.trim() || null
                : form.municipality || null;

            return {
              ...base,
              setback_front: feetToMetres(form.setback_front),
              setback_rear: feetToMetres(form.setback_rear),
              setback_left: feetToMetres(form.setback_left),
              setback_right: feetToMetres(form.setback_right),
              road_side: form.road_side,
              north_direction: OPPOSITE[form.road_side],
              num_bedrooms: parseInt(form.num_bedrooms, 10),
              toilets: parseInt(form.toilets, 10),
              parking: form.parking,
              city: form.city,
              municipality: resolvedMunicipality,
              road_width_m: Math.round(parseFloat(form.road_width_m) * 0.3048),
              has_pooja: form.has_pooja,
              has_study: form.has_study,
              has_balcony: form.has_balcony,
              num_floors: parseInt(form.num_floors, 10),
              has_stilt: form.has_stilt,
              has_basement: form.has_basement,
              vastu_enabled: form.vastu_enabled,
            };
          })()
        ),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail ?? "Failed to update project.");
      }

      router.push(`/projects/${project.id}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      {/* Page header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">Edit Project</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Update plot details — layouts will be regenerated on save.
        </p>
      </div>

      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-8 md:rounded-2xl md:border md:border-border md:bg-card/30 md:p-8"
      >
        {/* ── 1. Project name ───────────────────────────────────────────── */}
        <div className="flex flex-col gap-4">
          <Section num="1" title="Project" />
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="name">Project name</Label>
            <Input
              id="name"
              required
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
            />
          </div>
        </div>

        {/* ── 2. Plot & city ────────────────────────────────────────────── */}
        <div className="flex flex-col gap-4">
          <Section num="2" title="Plot Dimensions" />

          {/* Plot shape selector */}
          <div className="flex flex-col gap-1.5">
            <Label>Plot shape</Label>
            <div className="flex gap-3">
              {(
                [
                  { value: "rectangular", label: "Rectangular", desc: "Standard 4-sided plot" },
                  { value: "trapezoid", label: "Trapezoid", desc: "Different front & rear widths" },
                  {
                    value: "quadrilateral",
                    label: "Quadrilateral",
                    desc: "Any convex 4-corner shape",
                  },
                ] as { value: string; label: string; desc: string }[]
              ).map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => set("plot_shape", opt.value)}
                  className={[
                    "flex-1 rounded-lg border px-4 py-3 text-left text-sm transition-colors",
                    form.plot_shape === opt.value
                      ? "border-primary bg-primary/5 ring-1 ring-primary"
                      : "border-border bg-background hover:bg-muted",
                  ].join(" ")}
                >
                  <span className="font-medium">{opt.label}</span>
                  <span className="block text-xs text-muted-foreground mt-0.5">{opt.desc}</span>
                </button>
              ))}
            </div>
          </div>

          {form.plot_shape !== "quadrilateral" && (
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="plot_length">Length / Depth (feet)</Label>
                <Input
                  id="plot_length"
                  type="number"
                  min="16"
                  step="0.1"
                  required
                  value={form.plot_length}
                  onChange={(e) => set("plot_length", e.target.value)}
                />
              </div>
              {form.plot_shape === "rectangular" ? (
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="plot_width">Width (feet)</Label>
                  <Input
                    id="plot_width"
                    type="number"
                    min="16"
                    step="0.1"
                    required
                    value={form.plot_width}
                    onChange={(e) => set("plot_width", e.target.value)}
                  />
                </div>
              ) : (
                <div className="flex flex-col gap-1.5">
                  <Label className="invisible text-xs">spacer</Label>
                  <p className="flex h-9 items-center text-xs text-muted-foreground">
                    Enter front &amp; rear widths below
                  </p>
                </div>
              )}
            </div>
          )}

          {form.plot_shape === "trapezoid" && (
            <div className="grid grid-cols-2 gap-4 rounded-lg border bg-muted/30 p-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="plot_front_width">Front Width (feet)</Label>
                <Input
                  id="plot_front_width"
                  type="number"
                  min="10"
                  step="0.1"
                  placeholder="30"
                  required
                  value={form.plot_front_width}
                  onChange={(e) => set("plot_front_width", e.target.value)}
                />
                <p className="text-xs text-muted-foreground">Road-facing side</p>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="plot_rear_width">Rear Width (feet)</Label>
                <Input
                  id="plot_rear_width"
                  type="number"
                  min="10"
                  step="0.1"
                  placeholder="25"
                  required
                  value={form.plot_rear_width}
                  onChange={(e) => set("plot_rear_width", e.target.value)}
                />
                <p className="text-xs text-muted-foreground">Opposite side</p>
              </div>
            </div>
          )}
          {form.plot_shape === "quadrilateral" && (
            <div className="flex flex-col gap-3 rounded-lg border bg-muted/30 p-4">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Corner coordinates (metres, CCW from front-left)
              </p>
              {(
                [
                  { label: "Front-Left (0, 0 — fixed)", idx: 0 },
                  { label: "Front-Right", idx: 1 },
                  { label: "Rear-Right", idx: 2 },
                  { label: "Rear-Left", idx: 3 },
                ] as const
              ).map(({ label, idx }) => (
                <div key={label} className="flex items-center gap-3">
                  <span className="w-36 shrink-0 text-xs font-medium text-foreground">{label}</span>
                  <div className="flex gap-2">
                    <div className="flex flex-col gap-1">
                      <Label className="text-xs">X (m)</Label>
                      <Input
                        type="number"
                        step="0.1"
                        value={quadCorners[idx].x}
                        disabled={idx === 0}
                        onChange={(e) => setQuadCorner(idx, "x", e.target.value)}
                        className="w-24"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <Label className="text-xs">Y (m)</Label>
                      <Input
                        type="number"
                        step="0.1"
                        value={quadCorners[idx].y}
                        disabled={idx === 0}
                        onChange={(e) => setQuadCorner(idx, "y", e.target.value)}
                        className="w-24"
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="city">City / FAR & Setback tables</Label>
            <Select id="city" value={form.city} onChange={(e) => set("city", e.target.value)}>
              {CITIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="municipality">Municipality / Building Authority</Label>
            <Select
              id="municipality"
              value={form.municipality}
              onChange={(e) => set("municipality", e.target.value)}
            >
              {MUNICIPALITIES.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </Select>
            <p className="text-xs text-muted-foreground">
              Applies bye-law specific ground coverage, FAR, and height limits.
            </p>
          </div>

          {form.municipality === "Other" && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="municipality_other">Specify authority name</Label>
              <input
                id="municipality_other"
                type="text"
                placeholder="e.g. Trichy Corporation (TCC)"
                value={form.municipality_other}
                onChange={(e) => set("municipality_other", e.target.value)}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
            </div>
          )}
        </div>

        {/* ── 3. Orientation & setbacks ─────────────────────────────────── */}
        <div className="flex flex-col gap-4">
          <Section num="3" title="Orientation & Setbacks" />
          <div className="flex gap-6 items-start">
            <div className="shrink-0 w-28 h-28 rounded-xl border bg-card p-1.5">
              <PlotCompass roadSide={form.road_side} />
            </div>
            <div className="flex-1 flex flex-col gap-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="road_side">Road facing</Label>
                  <Select
                    id="road_side"
                    value={form.road_side}
                    onChange={(e) => set("road_side", e.target.value)}
                  >
                    {DIRECTIONS.map((d) => (
                      <option key={d} value={d}>
                        {DIRECTION_LABELS[d]}
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="road_width_m">Road width (ft)</Label>
                  <Input
                    id="road_width_m"
                    type="number"
                    min="10"
                    step="1"
                    value={form.road_width_m}
                    onChange={(e) => set("road_width_m", e.target.value)}
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-lg border bg-muted/30 p-4">
            <p className="text-xs font-medium text-muted-foreground mb-3 uppercase tracking-wide">
              Setbacks (feet)
            </p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {(["front", "rear", "left", "right"] as const).map((side) => (
                <div key={side} className="flex flex-col gap-1.5">
                  <Label htmlFor={`setback_${side}`} className="capitalize text-xs">
                    {side}
                  </Label>
                  <Input
                    id={`setback_${side}`}
                    type="number"
                    min="0"
                    step="0.1"
                    required
                    value={form[`setback_${side}`]}
                    onChange={(e) => set(`setback_${side}`, e.target.value)}
                  />
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── 4. Configuration ──────────────────────────────────────────── */}
        <div className="flex flex-col gap-4">
          <Section num="4" title="Configuration" />
          <div className="grid grid-cols-3 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="num_bedrooms">Bedrooms</Label>
              <Select
                id="num_bedrooms"
                value={form.num_bedrooms}
                onChange={(e) => set("num_bedrooms", e.target.value)}
              >
                {[1, 2, 3, 4, 5, 6].map((n) => (
                  <option key={n} value={n}>
                    {n} BHK
                  </option>
                ))}
              </Select>
              {parseInt(form.num_bedrooms, 10) >= 4 && (
                <p className="text-xs text-amber-700 dark:text-amber-400">
                  4BHK requires minimum 200 sqm (≈ 2,150 sq ft) plot area
                </p>
              )}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="toilets">Toilets</Label>
              <Select
                id="toilets"
                value={form.toilets}
                onChange={(e) => set("toilets", e.target.value)}
              >
                {[1, 2, 3, 4].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label className="invisible text-xs">Parking</Label>
              <div className="flex h-9 cursor-pointer items-center gap-2.5 rounded-md border bg-background px-3 text-sm hover:bg-muted transition-colors">
                <Checkbox
                  id="parking"
                  checked={form.parking}
                  onCheckedChange={(v) => set("parking", !!v)}
                  className="data-[state=checked]:bg-primary data-[state=checked]:border-primary"
                />
                <Label htmlFor="parking" className="cursor-pointer font-normal">
                  Parking
                </Label>
              </div>
            </div>
          </div>
        </div>

        {/* ── 5. Floor configuration ────────────────────────────────────── */}
        <div className="flex flex-col gap-4">
          <Section num="5" title="Floor Configuration" />
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Number of floors</Label>
              <div className="flex gap-2">
                {(
                  [
                    { value: "1", label: "G" },
                    { value: "2", label: "G+1" },
                    { value: "3", label: "G+2" },
                  ] as const
                ).map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => set("num_floors", opt.value)}
                    className={[
                      "rounded-lg border px-5 py-2 text-sm font-medium transition-colors",
                      form.num_floors === opt.value
                        ? "border-primary bg-primary/5 ring-1 ring-primary"
                        : "border-border bg-background hover:bg-muted",
                    ].join(" ")}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="flex cursor-pointer items-center gap-2.5 rounded-lg border bg-background px-4 py-3 text-sm hover:bg-muted transition-colors">
                <Checkbox
                  id="has_stilt"
                  checked={form.has_stilt}
                  onCheckedChange={(v) => set("has_stilt", !!v)}
                  className="data-[state=checked]:bg-primary data-[state=checked]:border-primary"
                />
                <Label htmlFor="has_stilt" className="cursor-pointer font-normal">
                  Stilt floor (parking only)
                </Label>
              </div>
              <div className="flex cursor-pointer items-center gap-2.5 rounded-lg border bg-background px-4 py-3 text-sm hover:bg-muted transition-colors">
                <Checkbox
                  id="has_basement"
                  checked={form.has_basement}
                  onCheckedChange={(v) => set("has_basement", !!v)}
                  className="data-[state=checked]:bg-primary data-[state=checked]:border-primary"
                />
                <Label htmlFor="has_basement" className="cursor-pointer font-normal">
                  Basement (−1)
                </Label>
              </div>
            </div>
          </div>
        </div>

        {/* ── 6. Optional rooms ─────────────────────────────────────────── */}
        <div className="flex flex-col gap-4">
          <Section num="6" title="Optional Rooms" />
          <div className="grid grid-cols-3 gap-3">
            {(
              [
                { field: "has_pooja", label: "Pooja room" },
                { field: "has_study", label: "Study room" },
                { field: "has_balcony", label: "Balcony" },
              ] as const
            ).map(({ field, label }) => (
              <div
                key={field}
                className="flex cursor-pointer items-center gap-2.5 rounded-lg border bg-background px-4 py-3 text-sm hover:bg-muted transition-colors"
              >
                <Checkbox
                  id={field}
                  checked={form[field]}
                  onCheckedChange={(v) => set(field, !!v)}
                  className="data-[state=checked]:bg-primary data-[state=checked]:border-primary"
                />
                <Label htmlFor={field} className="cursor-pointer font-normal">
                  {label}
                </Label>
              </div>
            ))}
          </div>
        </div>

        {/* ── 7. Vastu compliance ───────────────────────────────────────── */}
        <div className="flex flex-col gap-4">
          <Section num="7" title="Vastu Compliance" />
          <div className="flex items-center justify-between rounded-lg border bg-background px-4 py-3">
            <div>
              <Label htmlFor="vastu_enabled" className="font-medium">
                Vastu Compliance
              </Label>
              <p className="text-xs text-muted-foreground mt-0.5">
                Check room placement against Vastu Shastra principles
              </p>
            </div>
            <Switch
              id="vastu_enabled"
              checked={form.vastu_enabled}
              onCheckedChange={(v) => set("vastu_enabled", v)}
            />
          </div>
          {form.vastu_enabled && (
            <div className="rounded-lg border border-orange-500/30 bg-orange-500/5 px-4 py-3 text-xs text-orange-700 dark:text-orange-400">
              Vastu analysis checks room zones against Vastu Shastra principles (NE sacred zone, SE
              kitchen, SW master bedroom, etc.) and flags violations in layout compliance.
            </div>
          )}
        </div>

        {/* ── Submit ────────────────────────────────────────────────────── */}
        {error && (
          <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-2.5 text-sm text-destructive">
            {error}
          </p>
        )}

        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={loading || !session}
            className="flex-1 rounded-md bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground btn-shine shadow-md shadow-primary/20 hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {loading ? "Saving…" : "Save & regenerate layouts"}
          </button>
          <button
            type="button"
            onClick={() => router.push(`/projects/${project.id}`)}
            className="rounded-md border px-4 py-2.5 text-sm font-medium hover:bg-muted transition-colors"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
