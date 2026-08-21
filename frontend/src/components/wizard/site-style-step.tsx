"use client";

/**
 * Wizard "Site & Style" step — Task 24 of the solver-capability-uplift plan.
 *
 * Standalone controlled component: it owns its field state and reports the
 * full GenerateRequest-shaped payload up through `onChange`. Wiring into the
 * live wizard (`app/(app)/projects/new/new-project-form.tsx`) lands with the
 * GenerateRequest flow — see "Task 24 rulings" in the plan.
 *
 * Style presets are fetched from GET /api/backend/style-presets and are soft
 * defaults only: a flag is pre-ticked when its corpus prevalence is at least
 * PRE_TICK_THRESHOLD, and any checkbox the user explicitly touched is never
 * re-ticked by a later style change (spec §6: the style signal is weak, so
 * every helper text quotes the real percentage).
 */

import { useCallback, useEffect, useState } from "react";

import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";

export type PlotTemplate = "RECT" | "L";
export type GateSide = "N" | "S" | "E" | "W";

export interface SiteStyleValue {
  plotTemplate: PlotTemplate;
  notchWidth: number | null;
  notchDepth: number | null;
  northAngleDeg: number;
  stylePreset: string | null;
  programme: Set<string>;
  site: {
    compound_wall: boolean;
    landscaped_setbacks: boolean;
    gate_side: GateSide | null;
  };
}

interface PresetPayload {
  median_plot_sqft: number;
  typical_bhk: string;
  prevalence: Record<string, number>;
}

const PROGRAMME_FLAGS = [
  "courtyard",
  "verandah",
  "car_porch_open",
  "pooja",
  "terrace",
  "study",
] as const;

const FLAG_LABELS: Record<(typeof PROGRAMME_FLAGS)[number], string> = {
  courtyard: "Central courtyard",
  verandah: "Verandah / osari",
  car_porch_open: "Car porch open",
  pooja: "Pooja room",
  terrace: "Terrace",
  study: "Study / library",
};

// A feature present in <25% of a style's designs is a bad default. Must match
// PRE_TICK_THRESHOLD in backend/app/engine/style_presets.py.
const PRE_TICK_THRESHOLD = 25;

/** Parity with vastu.py::road_side_for_north_angle — S/E/N/W at 0/90/180/270°,
 * null for anything off-cardinal (a surveyed bearing need not be cardinal). */
export function deriveRoadSide(angleDeg: number): GateSide | null {
  const a = ((angleDeg % 360) + 360) % 360;
  const idx = Math.round(a / 90) % 4;
  if (Math.abs(a - idx * 90) > 1e-6) return null;
  return (["S", "E", "N", "W"] as const)[idx];
}

function prevalenceLabel(pct: number): string {
  if (pct >= PRE_TICK_THRESHOLD) return `typical (${pct}%)`;
  if (pct > 0) return `uncommon (${pct}%)`;
  return "rare (0%)";
}

const INITIAL_VALUE: SiteStyleValue = {
  plotTemplate: "RECT",
  notchWidth: null,
  notchDepth: null,
  northAngleDeg: 0,
  stylePreset: null,
  programme: new Set(),
  site: { compound_wall: true, landscaped_setbacks: true, gate_side: "S" },
};

export function SiteStyleStep({ onChange }: { onChange: (value: SiteStyleValue) => void }) {
  const [value, setValue] = useState<SiteStyleValue>(INITIAL_VALUE);
  const [presets, setPresets] = useState<Record<string, PresetPayload>>({});
  // Flags the user clicked by hand; a later style change must not override them.
  const [touched, setTouched] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    fetch("/api/backend/style-presets")
      .then(async (res) => (res.ok ? res.json() : {}))
      .then((data) => {
        if (!cancelled) setPresets(data);
      })
      .catch(() => {
        // Presets are optional sugar; an empty picker still lets the user
        // tick programme flags manually.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const emit = useCallback(
    (next: SiteStyleValue) => {
      setValue(next);
      onChange(next);
    },
    [onChange]
  );

  function setField<K extends keyof SiteStyleValue>(field: K, v: SiteStyleValue[K]) {
    emit({ ...value, [field]: v });
  }

  function handleStyleChange(styleName: string) {
    const preset = presets[styleName] ?? null;
    const programme = new Set(value.programme);
    if (preset) {
      for (const flag of PROGRAMME_FLAGS) {
        if (touched.has(flag)) continue;
        const pct = preset.prevalence[flag] ?? 0;
        if (pct >= PRE_TICK_THRESHOLD) programme.add(flag);
        else programme.delete(flag);
      }
    }
    emit({ ...value, stylePreset: styleName || null, programme });
  }

  function toggleFlag(flag: (typeof PROGRAMME_FLAGS)[number], checked: boolean) {
    setTouched((prev) => new Set(prev).add(flag));
    const programme = new Set(value.programme);
    if (checked) programme.add(flag);
    else programme.delete(flag);
    setField("programme", programme);
  }

  const roadSide = deriveRoadSide(value.northAngleDeg);

  return (
    <div className="flex flex-col gap-6">
      {/* ── Plot shape ─────────────────────────────────────────────── */}
      <div className="flex flex-col gap-2">
        <Label>Plot shape</Label>
        <div className="grid grid-cols-2 gap-3">
          {(
            [
              { value: "RECT", label: "Rectangle" },
              { value: "L", label: "L-shaped" },
            ] as Array<{ value: PlotTemplate; label: string }>
          ).map((opt) => (
            <label
              key={opt.value}
              htmlFor={`plot-template-${opt.value}`}
              className="flex cursor-pointer items-center gap-2 rounded-lg border px-4 py-3 text-sm transition-colors hover:bg-muted"
            >
              <input
                id={`plot-template-${opt.value}`}
                type="radio"
                name="plot_template"
                value={opt.value}
                checked={value.plotTemplate === opt.value}
                onChange={() => setField("plotTemplate", opt.value)}
                className="accent-primary"
              />
              <span>{opt.label}</span>
            </label>
          ))}
        </div>
        {/* Task 9 ruling 1: T/U plots raise at the engine, so they are not offered. */}
        <p className="text-xs text-muted-foreground">
          An L-shaped plot is a rectangle with one rear corner cut out.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="notch-width">Notch width</Label>
          <Input
            id="notch-width"
            type="number"
            min="0.5"
            step="0.1"
            disabled={value.plotTemplate === "RECT"}
            value={value.notchWidth ?? ""}
            onChange={(e) =>
              setField("notchWidth", e.target.value ? Number.parseFloat(e.target.value) : null)
            }
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="notch-depth">Notch depth</Label>
          <Input
            id="notch-depth"
            type="number"
            min="0.5"
            step="0.1"
            disabled={value.plotTemplate === "RECT"}
            value={value.notchDepth ?? ""}
            onChange={(e) =>
              setField("notchDepth", e.target.value ? Number.parseFloat(e.target.value) : null)
            }
          />
        </div>
      </div>

      {/* ── Orientation ────────────────────────────────────────────── */}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="north-angle">North angle</Label>
        <Input
          id="north-angle"
          type="number"
          min="0"
          max="359"
          step="1"
          value={value.northAngleDeg}
          onChange={(e) =>
            setField(
              "northAngleDeg",
              (((Number.parseFloat(e.target.value) || 0) % 360) + 360) % 360
            )
          }
        />
        <p className="text-xs text-muted-foreground" aria-live="polite">
          Road side:{" "}
          <span data-testid="derived-road-side" className="font-medium">
            {roadSide ?? "— (non-cardinal)"}
          </span>
        </p>
      </div>

      {/* ── Style preset ───────────────────────────────────────────── */}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="style-preset">Style preset</Label>
        <Select
          id="style-preset"
          value={value.stylePreset ?? ""}
          onChange={(e) => handleStyleChange(e.target.value)}
        >
          <option value="">No preset</option>
          {Object.keys(presets)
            .sort()
            .map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
        </Select>
        <p className="text-xs text-muted-foreground">
          Seeds the programme below with what is typical for the style — every choice stays yours to
          override.
        </p>
      </div>

      {/* ── Programme ──────────────────────────────────────────────── */}
      <div className="flex flex-col gap-2">
        <Label>Programme</Label>
        {PROGRAMME_FLAGS.map((flag) => (
          <div key={flag} className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Checkbox
                id={`programme-${flag}`}
                checked={value.programme.has(flag)}
                onCheckedChange={(v) => toggleFlag(flag, v === true)}
              />
              <Label htmlFor={`programme-${flag}`} className="cursor-pointer font-normal">
                {FLAG_LABELS[flag]}
              </Label>
            </div>
            <span className="text-xs text-muted-foreground">
              {presets[value.stylePreset ?? ""]
                ? prevalenceLabel(presets[value.stylePreset ?? ""].prevalence[flag] ?? 0)
                : ""}
            </span>
          </div>
        ))}
      </div>

      {/* ── Site ───────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-2">
        <Label>Site</Label>
        <div className="flex items-center gap-2">
          <Checkbox
            id="site-compound-wall"
            checked={value.site.compound_wall}
            onCheckedChange={(v) => setField("site", { ...value.site, compound_wall: v === true })}
          />
          <Label htmlFor="site-compound-wall" className="cursor-pointer font-normal">
            Compound wall
          </Label>
        </div>
        <div className="flex items-center gap-2">
          <Checkbox
            id="site-landscaped-setbacks"
            checked={value.site.landscaped_setbacks}
            onCheckedChange={(v) =>
              setField("site", { ...value.site, landscaped_setbacks: v === true })
            }
          />
          <Label htmlFor="site-landscaped-setbacks" className="cursor-pointer font-normal">
            Landscaped setbacks
          </Label>
        </div>
        <div className="flex items-center gap-3">
          <Label htmlFor="site-gate-side" className="font-normal">
            Gate on
          </Label>
          <Select
            id="site-gate-side"
            className="w-32"
            value={value.site.gate_side ?? ""}
            onChange={(e) =>
              setField("site", {
                ...value.site,
                gate_side: (e.target.value || null) as GateSide | null,
              })
            }
          >
            <option value="">—</option>
            {(["N", "S", "E", "W"] as const).map((side) => (
              <option key={side} value={side}>
                {side}
              </option>
            ))}
          </Select>
        </div>
      </div>
    </div>
  );
}
