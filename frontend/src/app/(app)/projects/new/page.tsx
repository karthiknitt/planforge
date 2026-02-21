"use client";

import { Minus, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { useSession } from "@/lib/auth-client";
import { CITIES, type CustomRoomSpec, ROOM_TYPES } from "@/lib/layout-types";

const DIRECTIONS = ["N", "S", "E", "W"] as const;
const DIRECTION_LABELS: Record<string, string> = { N: "North", S: "South", E: "East", W: "West" };
const OPPOSITE: Record<string, string> = { N: "S", S: "N", E: "W", W: "E" };

const FLOOR_PREFS = [
  { value: "gf", label: "Ground Floor" },
  { value: "ff", label: "First Floor" },
  { value: "sf", label: "Second Floor" },
  { value: "either", label: "Any Floor" },
  { value: "basement", label: "Basement" },
  { value: "stilt", label: "Stilt" },
] as const;

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

/* ── Custom room row ───────────────────────────────────────────────────────── */
function CustomRoomRow({
  room,
  onChange,
  onRemove,
}: {
  room: CustomRoomSpec;
  onChange: (updated: CustomRoomSpec) => void;
  onRemove: () => void;
}) {
  return (
    <div className="grid grid-cols-[1fr_1fr_1fr_auto] gap-2 items-start">
      <div className="flex flex-col gap-1">
        <Select
          value={room.type}
          onChange={(e) => onChange({ ...room, type: e.target.value })}
          className="text-sm"
        >
          {ROOM_TYPES.map((rt) => (
            <option key={rt.value} value={rt.value}>
              {rt.label}
            </option>
          ))}
        </Select>
        <Input
          placeholder="Custom name"
          value={room.name ?? ""}
          onChange={(e) => onChange({ ...room, name: e.target.value || undefined })}
          className="text-xs h-7"
        />
      </div>
      <Input
        type="number"
        min="1"
        step="0.5"
        placeholder="Min area m²"
        value={room.min_area_sqm ?? ""}
        onChange={(e) =>
          onChange({
            ...room,
            min_area_sqm: e.target.value ? parseFloat(e.target.value) : undefined,
          })
        }
        className="text-sm"
      />
      <Select
        value={room.floor_preference ?? "either"}
        onChange={(e) =>
          onChange({
            ...room,
            floor_preference: e.target.value as CustomRoomSpec["floor_preference"],
          })
        }
        className="text-sm"
      >
        {FLOOR_PREFS.map((fp) => (
          <option key={fp.value} value={fp.value}>
            {fp.label}
          </option>
        ))}
      </Select>
      <button
        type="button"
        onClick={onRemove}
        className="flex h-9 w-9 items-center justify-center rounded-md border text-muted-foreground hover:bg-destructive/5 hover:text-destructive transition-colors"
        title="Remove room"
      >
        <Minus className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

/* ── Main page ─────────────────────────────────────────────────────────────── */
export default function NewProjectPage() {
  const router = useRouter();
  const { data: session } = useSession();

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [configMode, setConfigMode] = useState<"basic" | "advanced">("basic");
  const [customRooms, setCustomRooms] = useState<CustomRoomSpec[]>([]);

  const [form, setForm] = useState({
    name: "",
    plot_shape: "rectangular",
    plot_length: "",
    plot_width: "",
    plot_front_width: "",
    plot_rear_width: "",
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
    // Phase E — multi-floor
    num_floors: "1",
    has_stilt: false,
    has_basement: false,
    // Vastu
    vastu_enabled: false,
  });

  function set(field: string, value: string | boolean) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function switchToAdvanced() {
    // Pre-populate with standard rooms from basic config
    const rooms: CustomRoomSpec[] = [];
    const nbr = parseInt(form.num_bedrooms, 10);
    for (let i = 0; i < nbr; i++) {
      rooms.push({
        type: "bedroom",
        name: `Bedroom ${i + 1}`,
        floor_preference: i === 0 ? "gf" : "ff",
        mandatory: true,
      });
    }
    const nwc = parseInt(form.toilets, 10);
    for (let i = 0; i < nwc; i++) {
      rooms.push({
        type: "toilet",
        name: `Toilet ${i + 1}`,
        floor_preference: "either",
        mandatory: true,
      });
    }
    if (form.parking)
      rooms.push({ type: "parking", name: "Parking", floor_preference: "gf", mandatory: false });
    if (form.has_pooja)
      rooms.push({ type: "pooja", name: "Pooja Room", floor_preference: "gf", mandatory: false });
    if (form.has_study)
      rooms.push({ type: "study", name: "Study", floor_preference: "ff", mandatory: false });
    if (form.has_balcony)
      rooms.push({ type: "balcony", name: "Balcony", floor_preference: "ff", mandatory: false });
    setCustomRooms(rooms);
    setConfigMode("advanced");
  }

  function addCustomRoom() {
    setCustomRooms((prev) => [
      ...prev,
      { type: "bedroom", floor_preference: "either", mandatory: false },
    ]);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const payload: Record<string, unknown> = {
        name: form.name,
        plot_shape: form.plot_shape,
        plot_length: feetToMetres(form.plot_length),
        plot_width:
          form.plot_shape === "trapezoid"
            ? feetToMetres(
                String(
                  Math.max(
                    parseFloat(form.plot_front_width) || 0,
                    parseFloat(form.plot_rear_width) || 0
                  )
                )
              )
            : feetToMetres(form.plot_width),
        plot_front_width:
          form.plot_shape === "trapezoid" ? feetToMetres(form.plot_front_width) : null,
        plot_rear_width:
          form.plot_shape === "trapezoid" ? feetToMetres(form.plot_rear_width) : null,
        plot_side_offset: 0,
        setback_front: feetToMetres(form.setback_front),
        setback_rear: feetToMetres(form.setback_rear),
        setback_left: feetToMetres(form.setback_left),
        setback_right: feetToMetres(form.setback_right),
        road_side: form.road_side,
        north_direction: OPPOSITE[form.road_side],
        city: form.city,
        road_width_m: parseFloat(form.road_width_m),
        vastu_enabled: form.vastu_enabled,
        // Multi-floor
        num_floors: parseInt(form.num_floors, 10),
        has_stilt: form.has_stilt,
        has_basement: form.has_basement,
      };

      if (configMode === "advanced") {
        // Advanced mode: pass custom_room_config, derive num_bedrooms/toilets from it
        const beds = customRooms.filter(
          (r) => r.type === "bedroom" || r.type === "master_bedroom"
        ).length;
        const toilets = customRooms.filter((r) => r.type === "toilet").length;
        payload.num_bedrooms = Math.max(1, beds);
        payload.toilets = Math.max(1, toilets);
        payload.parking = customRooms.some((r) => r.type === "parking");
        payload.has_pooja = customRooms.some((r) => r.type === "pooja");
        payload.has_study = customRooms.some((r) => r.type === "study");
        payload.has_balcony = customRooms.some((r) => r.type === "balcony");
        payload.custom_room_config = customRooms;
      } else {
        payload.num_bedrooms = parseInt(form.num_bedrooms, 10);
        payload.toilets = parseInt(form.toilets, 10);
        payload.parking = form.parking;
        payload.has_pooja = form.has_pooja;
        payload.has_study = form.has_study;
        payload.has_balcony = form.has_balcony;
      }

      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-User-Id": session!.user.id },
        body: JSON.stringify(payload),
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
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-[#1e3a5f]">New Project</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Enter your plot details to generate NBC-compliant floor plan options.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-8">
        {/* ── 1. Project name ───────────────────────────────────────── */}
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

        {/* ── 2. Plot & city ────────────────────────────────────────── */}
        <div className="flex flex-col gap-4">
          <Section num="2" title="Plot Dimensions" />

          <div className="flex flex-col gap-1.5">
            <Label>Plot shape</Label>
            <div className="flex gap-3">
              {(
                [
                  { value: "rectangular", label: "Rectangular", desc: "Standard 4-sided plot" },
                  { value: "trapezoid", label: "Trapezoid", desc: "Different front & rear widths" },
                ] as const
              ).map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => set("plot_shape", opt.value)}
                  className={[
                    "flex-1 rounded-lg border px-4 py-3 text-left text-sm transition-colors",
                    form.plot_shape === opt.value
                      ? "border-[#f97316] bg-[#f97316]/5 ring-1 ring-[#f97316]"
                      : "border-border bg-background hover:bg-muted",
                  ].join(" ")}
                >
                  <span className="font-medium">{opt.label}</span>
                  <span className="block text-xs text-muted-foreground mt-0.5">{opt.desc}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="plot_length">Length / Depth (feet)</Label>
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
            {form.plot_shape === "rectangular" ? (
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
            ) : (
              <div className="flex flex-col gap-1.5">
                <Label className="invisible text-xs">spacer</Label>
                <p className="flex h-9 items-center text-xs text-muted-foreground">
                  Enter front & rear widths below
                </p>
              </div>
            )}
          </div>

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
              Applies city-specific setback tables and FAR limits.
            </p>
          </div>
        </div>

        {/* ── 3. Orientation & setbacks ──────────────────────────────── */}
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

        {/* ── 4. Floor configuration (Phase E) ──────────────────────── */}
        <div className="flex flex-col gap-4">
          <Section num="4" title="Floor Configuration" />

          <div className="flex flex-col gap-2">
            <Label>Number of floors</Label>
            <div className="flex gap-2">
              {(
                [
                  { value: "1", label: "G (Single)" },
                  { value: "2", label: "G+1 (Two)" },
                  { value: "3", label: "G+2 (Three)" },
                ] as const
              ).map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => set("num_floors", opt.value)}
                  className={[
                    "flex-1 rounded-lg border px-3 py-2.5 text-sm font-medium transition-colors",
                    form.num_floors === opt.value
                      ? "border-[#f97316] bg-[#f97316]/5 text-[#f97316]"
                      : "border-border hover:bg-muted",
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
                className="border-[#1e3a5f]/30 data-[state=checked]:bg-[#1e3a5f] data-[state=checked]:border-[#1e3a5f]"
              />
              <div>
                <Label htmlFor="has_stilt" className="cursor-pointer font-normal">
                  Stilt floor
                </Label>
                <p className="text-xs text-muted-foreground">Ground floor = parking only</p>
              </div>
            </div>
            <div className="flex cursor-pointer items-center gap-2.5 rounded-lg border bg-background px-4 py-3 text-sm hover:bg-muted transition-colors">
              <Checkbox
                id="has_basement"
                checked={form.has_basement}
                onCheckedChange={(v) => set("has_basement", !!v)}
                className="border-[#1e3a5f]/30 data-[state=checked]:bg-[#1e3a5f] data-[state=checked]:border-[#1e3a5f]"
              />
              <div>
                <Label htmlFor="has_basement" className="cursor-pointer font-normal">
                  Basement (−1)
                </Label>
                <p className="text-xs text-muted-foreground">Parking, gym, store allowed</p>
              </div>
            </div>
          </div>

          {form.has_stilt && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-xs text-amber-700 dark:text-amber-400">
              Stilt floor only allows parking, lift lobby, pump room, and electric room — no
              habitable spaces.
            </div>
          )}
          {form.has_basement && (
            <div className="rounded-lg border border-blue-500/30 bg-blue-500/5 px-4 py-3 text-xs text-blue-700 dark:text-blue-400">
              Basement allows parking, gym, store room, and utility. Mechanical ventilation required
              (no natural light).
            </div>
          )}
          {form.num_floors === "3" && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-xs text-amber-700 dark:text-amber-400">
              G+2 buildings require a structural engineer's review. PlanForge will generate layouts
              but cannot certify structural adequacy.
            </div>
          )}
        </div>

        {/* ── 5. Room configuration ─────────────────────────────────── */}
        <div className="flex flex-col gap-4">
          <Section num="5" title="Room Configuration" />

          {/* Mode toggle */}
          <div className="flex w-fit items-center gap-1 rounded-xl border border-border bg-muted/40 p-1">
            {(["basic", "advanced"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => (mode === "advanced" ? switchToAdvanced() : setConfigMode("basic"))}
                className={[
                  "rounded-lg px-4 py-1.5 text-sm font-medium transition-colors",
                  configMode === mode
                    ? "bg-background text-foreground shadow-sm"
                    : "hover:bg-background/50",
                ].join(" ")}
              >
                {mode === "basic" ? "Basic" : "Advanced"}
              </button>
            ))}
          </div>

          {configMode === "basic" ? (
            <>
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
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="toilets">Toilets</Label>
                  <Select
                    id="toilets"
                    value={form.toilets}
                    onChange={(e) => set("toilets", e.target.value)}
                  >
                    {[1, 2, 3, 4, 5, 6].map((n) => (
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
            </>
          ) : (
            <div className="flex flex-col gap-3">
              <div className="grid grid-cols-[1fr_1fr_1fr_auto] gap-2 text-xs font-medium text-muted-foreground px-1">
                <span>Room type / name</span>
                <span>Min area (m²)</span>
                <span>Floor preference</span>
                <span />
              </div>
              {customRooms.map((room, idx) => (
                <CustomRoomRow
                  key={`${room.type}-${idx}`}
                  room={room}
                  onChange={(updated) =>
                    setCustomRooms((prev) => prev.map((r, i) => (i === idx ? updated : r)))
                  }
                  onRemove={() => setCustomRooms((prev) => prev.filter((_, i) => i !== idx))}
                />
              ))}
              <button
                type="button"
                onClick={addCustomRoom}
                className="flex items-center gap-2 rounded-lg border border-dashed border-border px-4 py-3 text-sm text-muted-foreground hover:bg-muted transition-colors w-full"
              >
                <Plus className="h-4 w-4" />
                Add room
              </button>
              {customRooms.length === 0 && (
                <p className="text-xs text-muted-foreground text-center py-2">
                  No rooms added. Click "Add room" to start.
                </p>
              )}
            </div>
          )}

          {/* Vastu toggle */}
          <div className="flex cursor-pointer items-center gap-2.5 rounded-lg border bg-background px-4 py-3 text-sm hover:bg-muted transition-colors w-fit">
            <Checkbox
              id="vastu_enabled"
              checked={form.vastu_enabled}
              onCheckedChange={(v) => set("vastu_enabled", !!v)}
              className="border-[#1e3a5f]/30 data-[state=checked]:bg-[#1e3a5f] data-[state=checked]:border-[#1e3a5f]"
            />
            <Label htmlFor="vastu_enabled" className="cursor-pointer font-normal">
              Apply Vastu Shastra rules
            </Label>
          </div>
        </div>

        {/* ── Submit ────────────────────────────────────────────────── */}
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
