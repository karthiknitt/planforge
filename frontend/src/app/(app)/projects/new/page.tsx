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

/* ── Live plot compass ─────────────────────────────────────────────────────── */
function PlotCompass({ roadSide }: { roadSide: string }) {
  const arrowAngles: Record<string, number> = { N: 0, E: 90, S: 180, W: 270 };
  const roadPositions: Record<string, { x1: number; y1: number; x2: number; y2: number }> = {
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

  const road = roadPositions[roadSide] ?? roadPositions.S;
  const label = roadLabel[roadSide] ?? roadLabel.S;
  const northAngle = arrowAngles[OPPOSITE[roadSide]] ?? 0;

  return (
    <svg viewBox="0 0 120 120" className="w-full h-full" aria-label="Plot orientation compass">
      {/* Plot rectangle */}
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

      {/* Road highlight */}
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

      {/* North arrow */}
      <g transform={`translate(60,60) rotate(${northAngle})`}>
        <polygon points="0,-16 -4,0 0,-4 4,0" fill="#1e3a5f" />
        <polygon points="0,16 -4,0 0,4 4,0" fill="#CBD5E1" />
      </g>

      {/* N label */}
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

/* ── Main page ─────────────────────────────────────────────────────────────── */
export default function NewProjectPage() {
  const router = useRouter();
  const { data: session } = useSession();

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const [form, setForm] = useState({
    name: "",
    plot_length: "",
    plot_width: "",
    setback_front: "5",
    setback_rear: "5",
    setback_left: "3",
    setback_right: "3",
    road_side: "S",
    num_bedrooms: "2",
    toilets: "2",
    parking: false,
    city: "other",
    road_width_m: "9",
    has_pooja: false,
    has_study: false,
    has_balcony: false,
  });

  function set(field: string, value: string | boolean) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/projects`, {
        method: "POST",
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
          road_width_m: parseFloat(form.road_width_m),
          has_pooja: form.has_pooja,
          has_study: form.has_study,
          has_balcony: form.has_balcony,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail ?? "Failed to create project.");
      }

      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      {/* Page header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-[#1e3a5f]">New Project</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Enter your plot details to generate NBC-compliant floor plan options.
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
              placeholder="e.g. My House — Trichy 2026"
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
                placeholder="40"
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
                placeholder="30"
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
            <p className="text-xs text-muted-foreground">
              Applies city-specific setback tables and FAR limits. Use &ldquo;Other&rdquo; for NBC
              defaults.
            </p>
          </div>
        </div>

        {/* ── 3. Orientation & setbacks ─────────────────────────────────── */}
        <div className="flex flex-col gap-4">
          <Section num="3" title="Orientation & Setbacks" />
          <div className="flex gap-6 items-start">
            {/* Live compass */}
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
                    placeholder="30"
                    value={form.road_width_m}
                    onChange={(e) =>
                      set("road_width_m", String(Math.round(parseFloat(e.target.value) * 0.3048)))
                    }
                  />
                  <p className="text-xs text-muted-foreground">Affects FAR for some cities.</p>
                </div>
              </div>
            </div>
          </div>

          {/* Setbacks grid */}
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
            {loading ? "Creating project…" : "Create project & generate layouts"}
          </button>
          <button
            type="button"
            onClick={() => router.push("/dashboard")}
            className="rounded-md border px-4 py-2.5 text-sm font-medium hover:bg-muted transition-colors"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
