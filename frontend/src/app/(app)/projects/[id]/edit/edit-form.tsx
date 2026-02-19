"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { useSession } from "@/lib/auth-client";
import { CITIES } from "@/lib/layout-types";

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
  roadWidthM?: number;
  hasPooja?: boolean;
  hasStudy?: boolean;
  hasBalcony?: boolean;
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
        fill="#EFF6FF"
        stroke="#CBD5E1"
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
        <polygon points="0,-16 -4,0 0,-4 4,0" fill="#1e3a5f" />
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
            fill="#1e3a5f"
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
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#f97316]/10 text-xs font-bold text-[#f97316]">
        {num}
      </span>
      <span className="text-sm font-semibold text-[#1e3a5f] tracking-wide uppercase">{title}</span>
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

  const [form, setForm] = useState({
    name: project.name,
    plot_length: metresToFeet(project.plotLength),
    plot_width: metresToFeet(project.plotWidth),
    setback_front: metresToFeet(project.setbackFront),
    setback_rear: metresToFeet(project.setbackRear),
    setback_left: metresToFeet(project.setbackLeft),
    setback_right: metresToFeet(project.setbackRight),
    road_side: project.roadSide,
    num_bedrooms: String(project.numBedrooms),
    toilets: String(project.toilets),
    parking: project.parking,
    city: project.city ?? "other",
    road_width_m: String(Math.round((project.roadWidthM ?? 9) / 0.3048)),
    has_pooja: project.hasPooja ?? false,
    has_study: project.hasStudy ?? false,
    has_balcony: project.hasBalcony ?? false,
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
        body: JSON.stringify({
          name: form.name,
          plot_length: feetToMetres(form.plot_length),
          plot_width: feetToMetres(form.plot_width),
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
          road_width_m: Math.round(parseFloat(form.road_width_m) * 0.3048),
          has_pooja: form.has_pooja,
          has_study: form.has_study,
          has_balcony: form.has_balcony,
        }),
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
    <div className="mx-auto max-w-2xl px-4 py-10">
      {/* Page header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-[#1e3a5f]">Edit Project</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Update plot details — layouts will be regenerated on save.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-8">
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
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="plot_length">Length (feet)</Label>
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
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="city">City / Compliance rules</Label>
            <Select id="city" value={form.city} onChange={(e) => set("city", e.target.value)}>
              {CITIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </Select>
          </div>
        </div>

        {/* ── 3. Orientation & setbacks ─────────────────────────────────── */}
        <div className="flex flex-col gap-4">
          <Section num="3" title="Orientation & Setbacks" />
          <div className="flex gap-6 items-start">
            <div className="shrink-0 w-28 h-28 rounded-xl border bg-slate-50 p-1.5">
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
                <option value="1">1 BHK</option>
                <option value="2">2 BHK</option>
                <option value="3">3 BHK</option>
                <option value="4">4 BHK</option>
              </Select>
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
                  className="border-[#1e3a5f]/30 data-[state=checked]:bg-[#1e3a5f] data-[state=checked]:border-[#1e3a5f]"
                />
                <Label htmlFor="parking" className="cursor-pointer font-normal">
                  Parking
                </Label>
              </div>
            </div>
          </div>
        </div>

        {/* ── 5. Optional rooms ─────────────────────────────────────────── */}
        <div className="flex flex-col gap-4">
          <Section num="5" title="Optional Rooms" />
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
                  className="border-[#1e3a5f]/30 data-[state=checked]:bg-[#1e3a5f] data-[state=checked]:border-[#1e3a5f]"
                />
                <Label htmlFor={field} className="cursor-pointer font-normal">
                  {label}
                </Label>
              </div>
            ))}
          </div>
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
            className="flex-1 rounded-md bg-[#f97316] px-6 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-[#ea6c0a] disabled:opacity-50 transition-colors"
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
