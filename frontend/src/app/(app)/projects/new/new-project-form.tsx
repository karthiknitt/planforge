"use client";

import { Check, ChevronLeft, ChevronRight, Info, Minus, Plus } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { PlotPreview } from "@/components/plot-preview";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useSession } from "@/lib/auth-client";
import { CITIES, type CustomRoomSpec, MUNICIPALITIES, ROOM_TYPES } from "@/lib/layout-types";
import { useLocale } from "@/lib/locale-context";
import { showErrorToast, showToast } from "@/lib/toast";

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

// Fields consumed from GET /api/gallery/plans/{preset_id} (backend/app/api/routes/gallery.py)
interface GalleryPresetPlan {
  name: string;
  plot_length_ft: number;
  plot_width_ft: number;
  num_bedrooms: number;
  num_toilets: number;
  parking: boolean;
  city: string;
  municipality: string | null;
}

type WizardStepId = "plot" | "orientation" | "floors" | "rooms" | "review";

/* ── Live plot compass ─────────────────────────────────────────────────────── */
function PlotCompass({ roadSide }: { roadSide: string }) {
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
  // The diagram frame is fixed north-up (N=top, S=bottom, E=right, W=left);
  // only the ROAD line moves to the selected edge. The arrow always points up.
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
      <g transform="translate(60,60)">
        <polygon points="0,-16 -4,0 0,-4 4,0" fill="currentColor" className="text-foreground" />
        <polygon points="0,16 -4,0 0,4 4,0" fill="#CBD5E1" />
      </g>
      <text
        x={60}
        y={36}
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
    </svg>
  );
}

/* ── Step content header (lighter than the old numbered Section) ─────────────── */
function StepHeader({ title }: { title: string }) {
  return (
    <div className="flex items-center gap-3">
      <span
        className="text-sm font-bold text-foreground tracking-wide uppercase"
        style={{ fontFamily: "var(--font-display)" }}
      >
        {title}
      </span>
      <Separator className="flex-1 bg-border/40" />
    </div>
  );
}

/* ── Inline jargon tooltip ─────────────────────────────────────────────────── */
function HelpTip({ text }: { text: string }) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-muted-foreground/70 hover:text-foreground transition-colors"
            aria-label="More information"
          >
            <Info className="h-3.5 w-3.5" />
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-64 text-center">
          {text}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

/* ── Step indicator ────────────────────────────────────────────────────────── */
function StepIndicator({
  steps,
  current,
  maxReached,
  onJump,
}: {
  steps: Array<{ id: WizardStepId; label: string }>;
  current: number;
  maxReached: number;
  onJump: (idx: number) => void;
}) {
  return (
    <ol className="flex items-center" aria-label="Form steps">
      {steps.map((s, i) => {
        const complete = i < current;
        const active = i === current;
        const clickable = i <= maxReached && i !== current;
        return (
          <li key={s.id} className="flex flex-1 items-center last:flex-none">
            <button
              type="button"
              disabled={!clickable}
              onClick={() => clickable && onJump(i)}
              aria-current={active ? "step" : undefined}
              className={[
                "flex items-center gap-2 rounded-lg px-1.5 py-1 text-left transition-colors",
                clickable ? "cursor-pointer hover:bg-muted" : "cursor-default",
              ].join(" ")}
            >
              <span
                className={[
                  "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ring-1 transition-colors",
                  complete
                    ? "bg-primary text-primary-foreground ring-primary"
                    : active
                      ? "bg-primary/10 text-primary ring-primary"
                      : "bg-muted text-muted-foreground ring-border",
                ].join(" ")}
              >
                {complete ? <Check className="h-3.5 w-3.5" /> : i + 1}
              </span>
              <span
                className={[
                  "hidden text-xs font-medium sm:inline",
                  active ? "text-foreground" : "text-muted-foreground",
                ].join(" ")}
              >
                {s.label}
              </span>
            </button>
            {i < steps.length - 1 && (
              <span
                className={["mx-1 h-px flex-1", complete ? "bg-primary" : "bg-border"].join(" ")}
              />
            )}
          </li>
        );
      })}
    </ol>
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
  const { t } = useLocale();

  const [error, setError] = useState("");
  const [stepError, setStepError] = useState("");
  const [loading, setLoading] = useState(false);
  const [configMode, setConfigMode] = useState<"basic" | "advanced">("basic");
  const [customRooms, setCustomRooms] = useState<CustomRoomSpec[]>([]);
  const [step, setStep] = useState(0);
  const [maxStepReached, setMaxStepReached] = useState(0);
  const [mobilePreviewOpen, setMobilePreviewOpen] = useState(false);
  // Quadrilateral corners: [FL fixed, FR, RR, RL] in metres
  const [quadCorners, setQuadCorners] = useState([
    { x: "0", y: "0" }, // Front-Left (fixed)
    { x: "", y: "0" }, // Front-Right
    { x: "", y: "" }, // Rear-Right
    { x: "0", y: "" }, // Rear-Left
  ]);

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
    attached_toilets: false,
    city: "other",
    municipality: "",
    municipality_other: "",
    road_width_m: "30",
    has_pooja: false,
    has_study: false,
    has_balcony: false,
    // Phase E — multi-floor
    num_floors: "1",
    has_stilt: false,
    has_basement: false,
    // Vastu
    vastu_enabled: false,
    // L-shaped cutout
    cutout_corner: "NE",
    cutout_width: "",
    cutout_height: "",
  });

  function set(field: string, value: string | boolean) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  // Prefill from a gallery "Use this template" CTA (?template=<preset-id>)
  const searchParams = useSearchParams();
  const template = searchParams.get("template");

  useEffect(() => {
    if (!template) return;
    let cancelled = false;
    fetch(`/api/backend/gallery/plans/${template}`)
      .then(async (res) => {
        if (cancelled) return;
        if (!res.ok) {
          showErrorToast(t("project.templateLoadFailed"));
          return;
        }
        const plan: GalleryPresetPlan = await res.json();
        if (cancelled) return;
        setForm((prev) => ({
          ...prev,
          name: plan.name,
          plot_length: String(plan.plot_length_ft),
          plot_width: String(plan.plot_width_ft),
          num_bedrooms: String(plan.num_bedrooms),
          toilets: String(plan.num_toilets),
          parking: plan.parking,
          city: plan.city === "Generic" ? "other" : plan.city.toLowerCase(),
          municipality: plan.municipality ?? "",
        }));
      })
      .catch(() => {
        // Network failure reaching the backend — same user-facing notice as a 404.
        if (!cancelled) showErrorToast(t("project.templateLoadFailed"));
      });
    return () => {
      cancelled = true;
    };
  }, [template, t]);

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

  /* ── Per-step validation (gates "Next", reuses the exact same geometric
   * checks the submit handler performs so a step can never be left in a
   * state the backend would reject) ────────────────────────────────────── */
  function validatePlotStep(): string | null {
    if (!form.name.trim()) return "Project name is required.";
    if (form.plot_shape === "quadrilateral") {
      const missing = quadCorners.some((c, i) => (i > 0 && c.x === "") || (i > 1 && c.y === ""));
      if (missing) return "Enter all corner coordinates.";
      const pts = quadCorners.map(
        (c) => [parseFloat(c.x) || 0, parseFloat(c.y) || 0] as [number, number]
      );
      if (!isConvex(pts)) return "Quadrilateral corners must form a convex polygon.";
      if (polygonArea(pts) < 30) return "Plot area must be at least 30 sqm.";
    } else if (form.plot_shape === "l_shaped") {
      if (!(parseFloat(form.plot_length) > 0) || !(parseFloat(form.plot_width) > 0)) {
        return "Enter plot length and width.";
      }
      const cw = feetToMetres(form.cutout_width);
      const ch = feetToMetres(form.cutout_height);
      const pl = feetToMetres(form.plot_length);
      const pw = feetToMetres(form.plot_width);
      if (!(cw > 0) || !(ch > 0)) {
        return "Cutout width and height must be greater than 0 for L-shaped plots.";
      }
      if (cw >= pw || ch >= pl) {
        return "Cutout dimensions must be smaller than the overall plot dimensions.";
      }
    } else if (form.plot_shape === "trapezoid") {
      if (!(parseFloat(form.plot_length) > 0)) return "Enter plot length.";
      if (!(parseFloat(form.plot_front_width) > 0) || !(parseFloat(form.plot_rear_width) > 0)) {
        return "Enter front and rear widths.";
      }
    } else {
      if (!(parseFloat(form.plot_length) > 0) || !(parseFloat(form.plot_width) > 0)) {
        return "Enter plot length and width.";
      }
    }
    return null;
  }

  function validateOrientationStep(): string | null {
    const sides = ["front", "rear", "left", "right"] as const;
    for (const side of sides) {
      const key = `setback_${side}` as keyof typeof form;
      if (!(parseFloat(form[key] as string) >= 0)) return "Enter valid setback values.";
    }
    if (!(parseFloat(form.road_width_m) > 0)) return "Enter road width.";
    return null;
  }

  function validateRoomsStep(): string | null {
    if (configMode === "advanced") {
      if (customRooms.length === 0) return "Add at least one room.";
      const hasBedroom = customRooms.some(
        (r) => r.type === "bedroom" || r.type === "master_bedroom"
      );
      if (!hasBedroom) return "Add at least one bedroom.";
    } else if (!(parseInt(form.num_bedrooms, 10) >= 1)) {
      return "Select at least one bedroom.";
    }
    return null;
  }

  const STEPS: Array<{
    id: WizardStepId;
    label: string;
    validate: () => string | null;
  }> = [
    { id: "plot", label: t("project.wizardStepPlot"), validate: validatePlotStep },
    {
      id: "orientation",
      label: t("project.wizardStepOrientation"),
      validate: validateOrientationStep,
    },
    { id: "floors", label: t("project.wizardStepFloors"), validate: () => null },
    { id: "rooms", label: t("project.wizardStepRooms"), validate: validateRoomsStep },
    { id: "review", label: t("project.wizardStepReview"), validate: () => null },
  ];

  function goNext() {
    const err = STEPS[step].validate();
    if (err) {
      setStepError(err);
      return;
    }
    setStepError("");
    const next = Math.min(step + 1, STEPS.length - 1);
    setStep(next);
    setMaxStepReached((m) => Math.max(m, next));
  }

  function goBack() {
    setStepError("");
    setStep((s) => Math.max(s - 1, 0));
  }

  function jumpTo(idx: number) {
    setStepError("");
    setStep(idx);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const payload: Record<string, unknown> = {
        name: form.name,
        plot_shape: form.plot_shape,
        plot_side_offset: 0,
      };

      if (form.plot_shape === "quadrilateral") {
        const pts = quadCorners.map(
          (c) => [parseFloat(c.x) || 0, parseFloat(c.y) || 0] as [number, number]
        );
        if (!isConvex(pts)) {
          setError("Quadrilateral corners must form a convex polygon.");
          setLoading(false);
          return;
        }
        if (polygonArea(pts) < 30) {
          setError("Plot area must be at least 30 sqm.");
          setLoading(false);
          return;
        }
        const xs = pts.map(([x]) => x);
        const ys = pts.map(([, y]) => y);
        payload.plot_corners = pts;
        payload.plot_length = Math.max(...ys);
        payload.plot_width = Math.max(...xs);
        payload.plot_front_width = null;
        payload.plot_rear_width = null;
        payload.cutout_width = 0;
        payload.cutout_height = 0;
      } else if (form.plot_shape === "l_shaped") {
        const cw = feetToMetres(form.cutout_width);
        const ch = feetToMetres(form.cutout_height);
        const pl = feetToMetres(form.plot_length);
        const pw = feetToMetres(form.plot_width);
        if (cw <= 0 || ch <= 0) {
          setError("Cutout width and height must be greater than 0 for L-shaped plots.");
          setLoading(false);
          return;
        }
        if (cw >= pw || ch >= pl) {
          setError("Cutout dimensions must be smaller than the overall plot dimensions.");
          setLoading(false);
          return;
        }
        payload.plot_length = pl;
        payload.plot_width = pw;
        payload.plot_front_width = null;
        payload.plot_rear_width = null;
        payload.cutout_corner = form.cutout_corner;
        payload.cutout_width = cw;
        payload.cutout_height = ch;
      } else {
        payload.plot_length = feetToMetres(form.plot_length);
        payload.plot_width =
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
        payload.plot_front_width =
          form.plot_shape === "trapezoid" ? feetToMetres(form.plot_front_width) : null;
        payload.plot_rear_width =
          form.plot_shape === "trapezoid" ? feetToMetres(form.plot_rear_width) : null;
        payload.cutout_width = 0;
        payload.cutout_height = 0;
      }

      const resolvedMunicipality =
        form.municipality === "Other"
          ? form.municipality_other.trim() || null
          : form.municipality || null;

      Object.assign(payload, {
        setback_front: feetToMetres(form.setback_front),
        setback_rear: feetToMetres(form.setback_rear),
        setback_left: feetToMetres(form.setback_left),
        setback_right: feetToMetres(form.setback_right),
        road_side: form.road_side,
        north_direction: OPPOSITE[form.road_side],
        city: form.city,
        municipality: resolvedMunicipality,
        road_width_m: Math.round(parseFloat(form.road_width_m) * 0.3048),
        vastu_enabled: form.vastu_enabled,
        // Multi-floor
        num_floors: parseInt(form.num_floors, 10),
        has_stilt: form.has_stilt,
        has_basement: form.has_basement,
      });

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
        payload.attached_toilets = form.attached_toilets;
      }

      const res = await fetch(`/api/backend/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail ?? "Failed to create project.");
      }

      const created = await res.json();
      showToast("success", "Project created");
      router.push(`/projects/${created.id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong.";
      setError(message);
      showErrorToast(message);
      setLoading(false);
    }
  }

  const activeId = STEPS[step].id;
  const showPreviewPane =
    activeId === "plot" || activeId === "orientation" || activeId === "floors";
  const previewSupportedShape = form.plot_shape === "rectangular" || form.plot_shape === "l_shaped";

  const previewPane = (
    <div className="rounded-lg border bg-muted/30 p-4">
      <p className="text-xs font-medium text-muted-foreground mb-3 uppercase tracking-wide">
        Plot Preview
      </p>
      {previewSupportedShape ? (
        <PlotPreview
          input={{
            plotLengthFt: form.plot_length,
            plotWidthFt: form.plot_width,
            setbackFrontFt: form.setback_front,
            setbackRearFt: form.setback_rear,
            setbackLeftFt: form.setback_left,
            setbackRightFt: form.setback_right,
            roadSide: form.road_side,
          }}
        />
      ) : (
        <div className="flex h-[260px] items-center justify-center rounded-md border border-dashed text-xs text-muted-foreground text-center px-4">
          Live preview is available for rectangular and L-shaped plots
        </div>
      )}
    </div>
  );

  return (
    <div className="mx-auto max-w-5xl px-4 sm:px-6 py-10 sm:py-14">
      <div className="mb-8">
        <h1
          className="text-2xl sm:text-3xl font-black text-foreground mb-2"
          style={{ fontFamily: "var(--font-display)" }}
        >
          {t("project.newProject")}
        </h1>
        <p className="text-sm text-muted-foreground">{t("project.newProjectHint")}</p>
      </div>

      <div className="mb-2 sm:hidden text-xs font-medium text-muted-foreground">
        {t("project.wizardStep")} {step + 1} {t("project.wizardOf")} {STEPS.length} —{" "}
        {STEPS[step].label}
      </div>
      <div className="mb-8 md:rounded-2xl md:border md:border-border/40 md:bg-card/20 md:p-4">
        <StepIndicator steps={STEPS} current={step} maxReached={maxStepReached} onJump={jumpTo} />
      </div>

      <form
        onSubmit={handleSubmit}
        onKeyDown={(e) => {
          if (e.key === "Enter" && activeId !== "review") {
            const target = e.target as HTMLElement;
            if (target.tagName !== "TEXTAREA") e.preventDefault();
          }
        }}
        className="flex flex-col gap-8 lg:grid lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start lg:gap-8"
      >
        <div className="flex flex-col gap-8 md:rounded-2xl md:border md:border-border/40 md:bg-card/20 md:p-8 lg:p-10">
          {/* ── Plot step ─────────────────────────────────────────────── */}
          {activeId === "plot" && (
            <>
              <div className="flex flex-col gap-4">
                <StepHeader title={t("project.newProject")} />
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="name">{t("project.projectName")}</Label>
                  <Input
                    id="name"
                    placeholder={t("project.projectNamePlaceholder")}
                    required
                    value={form.name}
                    onChange={(e) => set("name", e.target.value)}
                  />
                </div>
              </div>

              <div className="flex flex-col gap-4">
                <StepHeader title={t("project.plotDimensions")} />

                <div className="flex flex-col gap-1.5">
                  <Label>{t("project.plotShape")}</Label>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {(
                      [
                        {
                          value: "rectangular",
                          label: t("project.rectangular"),
                          desc: t("project.rectangularDesc"),
                        },
                        {
                          value: "trapezoid",
                          label: t("project.trapezoid"),
                          desc: t("project.trapezoidDesc"),
                        },
                        {
                          value: "l_shaped",
                          label: "L-Shaped",
                          desc: "Rectangle with corner cutout",
                        },
                        {
                          value: "quadrilateral",
                          label: t("project.quadrilateral"),
                          desc: t("project.quadrilateralDesc"),
                        },
                      ] as Array<{
                        value: "rectangular" | "trapezoid" | "l_shaped" | "quadrilateral";
                        label: string;
                        desc: string;
                      }>
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
                        <span className="block text-xs text-muted-foreground mt-0.5">
                          {opt.desc}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="plot_length">{t("project.plotLength")}</Label>
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
                  {form.plot_shape === "rectangular" || form.plot_shape === "l_shaped" ? (
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor="plot_width">{t("project.plotWidth")}</Label>
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
                        {t("project.enterWidthsBelow")}
                      </p>
                    </div>
                  )}
                </div>

                {form.plot_shape === "trapezoid" && (
                  <div className="grid grid-cols-2 gap-4 rounded-lg border bg-muted/30 p-4">
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor="plot_front_width">{t("project.plotFrontWidth")}</Label>
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
                      <p className="text-xs text-muted-foreground">{t("project.roadFacingSide")}</p>
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor="plot_rear_width">{t("project.plotRearWidth")}</Label>
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
                      <p className="text-xs text-muted-foreground">{t("project.oppositeSide")}</p>
                    </div>
                  </div>
                )}

                {form.plot_shape === "l_shaped" && (
                  <div className="grid grid-cols-1 gap-4 rounded-lg border bg-muted/30 p-4">
                    <p className="text-xs text-muted-foreground">
                      An L-shaped plot is a rectangle with one corner cut out. Enter overall
                      dimensions above, then specify the corner and size of the cutout below.
                    </p>
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor="cutout_corner">Cutout corner</Label>
                      <Select
                        id="cutout_corner"
                        value={form.cutout_corner}
                        onChange={(e) => set("cutout_corner", e.target.value)}
                      >
                        <option value="NE">NE — Rear-Right corner</option>
                        <option value="NW">NW — Rear-Left corner</option>
                        <option value="SE">SE — Front-Right corner</option>
                        <option value="SW">SW — Front-Left corner</option>
                      </Select>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor="cutout_width">Cutout Width (feet)</Label>
                        <Input
                          id="cutout_width"
                          type="number"
                          min="1"
                          step="0.1"
                          placeholder="10"
                          required
                          value={form.cutout_width}
                          onChange={(e) => set("cutout_width", e.target.value)}
                        />
                        <p className="text-xs text-muted-foreground">
                          Must be less than plot width
                        </p>
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor="cutout_height">Cutout Height (feet)</Label>
                        <Input
                          id="cutout_height"
                          type="number"
                          min="1"
                          step="0.1"
                          placeholder="10"
                          required
                          value={form.cutout_height}
                          onChange={(e) => set("cutout_height", e.target.value)}
                        />
                        <p className="text-xs text-muted-foreground">
                          Must be less than plot length
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {form.plot_shape === "quadrilateral" && (
                  <div className="rounded-lg border bg-muted/30 p-4 flex flex-col gap-3">
                    <p className="text-xs text-muted-foreground flex items-start gap-1.5">
                      <span>{t("project.quadHint")}</span>
                      <HelpTip text={t("project.quadUnitsHelp")} />
                    </p>
                    {(
                      [
                        t("project.frontLeft"),
                        t("project.frontRight"),
                        t("project.rearRight"),
                        t("project.rearLeft"),
                      ] as const
                    ).map((label, idx) => (
                      <div
                        key={label}
                        className="grid grid-cols-[140px_1fr_1fr] items-center gap-3"
                      >
                        <span className="text-sm font-medium">{label}</span>
                        <div className="flex flex-col gap-1">
                          <Label className="text-xs">{t("project.xMetres")}</Label>
                          <Input
                            type="number"
                            step="0.1"
                            placeholder="0"
                            disabled={idx === 0}
                            required={idx > 0}
                            value={quadCorners[idx].x}
                            onChange={(e) => setQuadCorner(idx, "x", e.target.value)}
                          />
                        </div>
                        <div className="flex flex-col gap-1">
                          <Label className="text-xs">{t("project.yMetres")}</Label>
                          <Input
                            type="number"
                            step="0.1"
                            placeholder="0"
                            disabled={idx === 0 || idx === 1}
                            required={idx > 1}
                            value={quadCorners[idx].y}
                            onChange={(e) => setQuadCorner(idx, "y", e.target.value)}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="city">{t("project.city")}</Label>
                  <Select id="city" value={form.city} onChange={(e) => set("city", e.target.value)}>
                    {CITIES.map((c) => (
                      <option key={c.value} value={c.value}>
                        {c.label}
                      </option>
                    ))}
                  </Select>
                  <p className="text-xs text-muted-foreground">{t("project.cityHint")}</p>
                </div>

                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center gap-1.5">
                    <Label htmlFor="municipality">{t("project.municipality")}</Label>
                    <HelpTip text={t("project.municipalityHelp")} />
                  </div>
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
                  <p className="text-xs text-muted-foreground">{t("project.municipalityHint")}</p>
                </div>

                {form.municipality === "Other" && (
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="municipality_other">{t("project.specifyAuthority")}</Label>
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
            </>
          )}

          {/* ── Orientation step ──────────────────────────────────────── */}
          {activeId === "orientation" && (
            <div className="flex flex-col gap-4">
              <StepHeader title={t("project.orientationSetbacks")} />
              <div className="flex gap-6 items-start">
                <div className="shrink-0 w-28 h-28 rounded-xl border bg-card p-1.5">
                  <PlotCompass roadSide={form.road_side} />
                </div>
                <div className="flex-1 flex flex-col gap-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor="road_side">{t("project.roadFacing")}</Label>
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
                      <Label htmlFor="road_width_m">{t("project.roadWidth")}</Label>
                      <Input
                        id="road_width_m"
                        type="number"
                        min="10"
                        step="1"
                        placeholder="30"
                        value={form.road_width_m}
                        onChange={(e) => set("road_width_m", e.target.value)}
                      />
                      <p className="text-xs text-muted-foreground">{t("project.roadWidthHint")}</p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="rounded-lg border bg-muted/30 p-4">
                <div className="mb-3 flex items-center gap-1.5">
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                    {t("project.setbacks")}
                  </p>
                  <HelpTip text={t("project.setbackHelp")} />
                </div>
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

              {/* Preview shown inline on mobile (no sidebar there) */}
              <div className="lg:hidden">
                <button
                  type="button"
                  onClick={() => setMobilePreviewOpen((v) => !v)}
                  className="text-xs font-medium text-primary underline underline-offset-2"
                >
                  {mobilePreviewOpen
                    ? t("project.wizardPreviewHide")
                    : t("project.wizardPreviewShow")}
                </button>
                {mobilePreviewOpen && <div className="mt-3">{previewPane}</div>}
              </div>
            </div>
          )}

          {/* ── Floors step ───────────────────────────────────────────── */}
          {activeId === "floors" && (
            <div className="flex flex-col gap-4">
              <StepHeader title={t("project.floorConfiguration")} />

              <div className="flex flex-col gap-2">
                <Label>{t("project.numFloors")}</Label>
                <div className="flex gap-2">
                  {(
                    [
                      { value: "1", label: t("project.gSingle") },
                      { value: "2", label: t("project.g1Two") },
                      { value: "3", label: t("project.g2Three") },
                    ] as Array<{ value: "1" | "2" | "3"; label: string }>
                  ).map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => set("num_floors", opt.value)}
                      className={[
                        "flex-1 rounded-lg border px-3 py-2.5 text-sm font-medium transition-colors",
                        form.num_floors === opt.value
                          ? "border-primary bg-primary/5 text-primary"
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
                    className="data-[state=checked]:bg-primary data-[state=checked]:border-primary"
                  />
                  <div>
                    <div className="flex items-center gap-1.5">
                      <Label htmlFor="has_stilt" className="cursor-pointer font-normal">
                        {t("project.stiltFloor")}
                      </Label>
                      <HelpTip text={t("project.stiltHelp")} />
                    </div>
                    <p className="text-xs text-muted-foreground">{t("project.stiltFloorDesc")}</p>
                  </div>
                </div>
                <div className="flex cursor-pointer items-center gap-2.5 rounded-lg border bg-background px-4 py-3 text-sm hover:bg-muted transition-colors">
                  <Checkbox
                    id="has_basement"
                    checked={form.has_basement}
                    onCheckedChange={(v) => set("has_basement", !!v)}
                    className="data-[state=checked]:bg-primary data-[state=checked]:border-primary"
                  />
                  <div>
                    <Label htmlFor="has_basement" className="cursor-pointer font-normal">
                      {t("project.basementMinus1")}
                    </Label>
                    <p className="text-xs text-muted-foreground">{t("project.basementDesc")}</p>
                  </div>
                </div>
              </div>

              {form.has_stilt && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-xs text-amber-700 dark:text-amber-400">
                  {t("project.stiltWarning")}
                </div>
              )}
              {form.has_basement && (
                <div className="rounded-lg border border-border bg-muted/40 px-4 py-3 text-xs text-muted-foreground">
                  {t("project.basementNote")}
                </div>
              )}
              {form.num_floors === "3" && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-xs text-amber-700 dark:text-amber-400">
                  {t("project.g2Warning")}
                </div>
              )}

              <div className="lg:hidden">
                <button
                  type="button"
                  onClick={() => setMobilePreviewOpen((v) => !v)}
                  className="text-xs font-medium text-primary underline underline-offset-2"
                >
                  {mobilePreviewOpen
                    ? t("project.wizardPreviewHide")
                    : t("project.wizardPreviewShow")}
                </button>
                {mobilePreviewOpen && <div className="mt-3">{previewPane}</div>}
              </div>
            </div>
          )}

          {/* ── Rooms step ────────────────────────────────────────────── */}
          {activeId === "rooms" && (
            <div className="flex flex-col gap-4">
              <StepHeader title={t("project.roomConfiguration")} />

              {/* Mode toggle */}
              <div className="flex w-fit items-center gap-1 rounded-xl border border-border bg-muted/40 p-1">
                {(["basic", "advanced"] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() =>
                      mode === "advanced" ? switchToAdvanced() : setConfigMode("basic")
                    }
                    className={[
                      "rounded-lg px-4 py-1.5 text-sm font-medium transition-colors",
                      configMode === mode
                        ? "bg-background text-foreground shadow-sm"
                        : "hover:bg-background/50",
                    ].join(" ")}
                  >
                    {mode === "basic" ? t("project.basic") : t("project.advanced")}
                  </button>
                ))}
              </div>

              {configMode === "basic" ? (
                <>
                  <div className="grid grid-cols-3 gap-4">
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor="num_bedrooms">{t("project.bedrooms")}</Label>
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
                          {t("project.bhkWarning")}
                        </p>
                      )}
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor="toilets">{t("project.toilets")}</Label>
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
                          className="data-[state=checked]:bg-primary data-[state=checked]:border-primary"
                        />
                        <Label htmlFor="parking" className="cursor-pointer font-normal">
                          {t("project.parking")}
                        </Label>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between rounded-lg border bg-background px-4 py-3">
                    <div>
                      <Label htmlFor="attached_toilets" className="font-medium">
                        {t("project.attachedToilets")}
                      </Label>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {t("project.attachedToiletsDesc")}
                      </p>
                    </div>
                    <Checkbox
                      id="attached_toilets"
                      checked={form.attached_toilets}
                      onCheckedChange={(v) => set("attached_toilets", !!v)}
                      className="data-[state=checked]:bg-primary data-[state=checked]:border-primary"
                    />
                  </div>

                  <div className="grid grid-cols-3 gap-3">
                    {(
                      [
                        { field: "has_pooja", label: t("project.poojaRoom") },
                        { field: "has_study", label: t("project.studyRoom") },
                        { field: "has_balcony", label: t("project.balcony") },
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
                </>
              ) : (
                <div className="flex flex-col gap-3">
                  <div className="grid grid-cols-[1fr_1fr_1fr_auto] gap-2 text-xs font-medium text-muted-foreground px-1">
                    <span>{t("project.roomType")}</span>
                    <span>{t("project.minArea")}</span>
                    <span>{t("project.floorPreference")}</span>
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
                    {t("project.addRoom")}
                  </button>
                  {customRooms.length === 0 && (
                    <p className="text-xs text-muted-foreground text-center py-2">
                      {t("project.noRoomsAdded")}
                    </p>
                  )}
                </div>
              )}

              {/* Vastu toggle */}
              <div className="flex items-center justify-between rounded-lg border bg-background px-4 py-3">
                <div>
                  <Label htmlFor="vastu_enabled" className="font-medium">
                    {t("project.vastu")}
                  </Label>
                  <p className="text-xs text-muted-foreground mt-0.5">{t("project.vastuDesc")}</p>
                </div>
                <Switch
                  id="vastu_enabled"
                  checked={form.vastu_enabled}
                  onCheckedChange={(v) => set("vastu_enabled", v)}
                />
              </div>
              {form.vastu_enabled && (
                <div className="rounded-lg border border-orange-500/30 bg-orange-500/5 px-4 py-3 text-xs text-orange-700 dark:text-orange-400">
                  {t("project.vastuEnabled")}
                </div>
              )}
            </div>
          )}

          {/* ── Review step ───────────────────────────────────────────── */}
          {activeId === "review" && (
            <div className="flex flex-col gap-6">
              <StepHeader title={t("project.reviewTitle")} />

              <ReviewSection
                title={t("project.reviewPlot")}
                onEdit={() => jumpTo(0)}
                editLabel={t("project.reviewEditStep")}
              >
                <ReviewRow label={t("project.projectName")} value={form.name || "—"} />
                <ReviewRow
                  label={t("project.plotShape")}
                  value={
                    (
                      {
                        rectangular: t("project.rectangular"),
                        trapezoid: t("project.trapezoid"),
                        l_shaped: "L-Shaped",
                        quadrilateral: t("project.quadrilateral"),
                      } as Record<string, string>
                    )[form.plot_shape] ?? form.plot_shape
                  }
                />
                {form.plot_shape === "quadrilateral" ? (
                  <ReviewRow
                    label={t("project.quadHint")}
                    value={`${quadCorners.length} corners set`}
                  />
                ) : form.plot_shape === "trapezoid" ? (
                  <>
                    <ReviewRow
                      label={t("project.plotLength")}
                      value={`${form.plot_length || "—"} ft`}
                    />
                    <ReviewRow
                      label={t("project.plotFrontWidth")}
                      value={`${form.plot_front_width || "—"} ft`}
                    />
                    <ReviewRow
                      label={t("project.plotRearWidth")}
                      value={`${form.plot_rear_width || "—"} ft`}
                    />
                  </>
                ) : (
                  <>
                    <ReviewRow
                      label={t("project.plotLength")}
                      value={`${form.plot_length || "—"} ft`}
                    />
                    <ReviewRow
                      label={t("project.plotWidth")}
                      value={`${form.plot_width || "—"} ft`}
                    />
                  </>
                )}
                <ReviewRow
                  label={t("project.city")}
                  value={CITIES.find((c) => c.value === form.city)?.label ?? form.city}
                />
                <ReviewRow
                  label={t("project.municipality")}
                  value={
                    form.municipality === "Other"
                      ? form.municipality_other || "—"
                      : form.municipality || "—"
                  }
                />
              </ReviewSection>

              <ReviewSection
                title={t("project.reviewOrientation")}
                onEdit={() => jumpTo(1)}
                editLabel={t("project.reviewEditStep")}
              >
                <ReviewRow
                  label={t("project.roadFacing")}
                  value={DIRECTION_LABELS[form.road_side] ?? form.road_side}
                />
                <ReviewRow
                  label={t("project.setbacks")}
                  value={`F ${form.setback_front} / R ${form.setback_rear} / L ${form.setback_left} / R ${form.setback_right} ft`}
                />
                <ReviewRow label={t("project.roadWidth")} value={`${form.road_width_m} ft`} />
              </ReviewSection>

              <ReviewSection
                title={t("project.reviewFloors")}
                onEdit={() => jumpTo(2)}
                editLabel={t("project.reviewEditStep")}
              >
                <ReviewRow label={t("project.numFloors")} value={form.num_floors} />
                <ReviewRow label={t("project.stiltFloor")} value={form.has_stilt ? "Yes" : "No"} />
                <ReviewRow
                  label={t("project.basementMinus1")}
                  value={form.has_basement ? "Yes" : "No"}
                />
              </ReviewSection>

              <ReviewSection
                title={t("project.reviewRooms")}
                onEdit={() => jumpTo(3)}
                editLabel={t("project.reviewEditStep")}
              >
                {configMode === "basic" ? (
                  <>
                    <ReviewRow label={t("project.bedrooms")} value={`${form.num_bedrooms} BHK`} />
                    <ReviewRow label={t("project.toilets")} value={form.toilets} />
                    <ReviewRow label={t("project.parking")} value={form.parking ? "Yes" : "No"} />
                  </>
                ) : (
                  <ReviewRow
                    label={t("project.roomConfiguration")}
                    value={`${customRooms.length} rooms`}
                  />
                )}
                <ReviewRow label={t("project.vastu")} value={form.vastu_enabled ? "Yes" : "No"} />
              </ReviewSection>
            </div>
          )}

          {/* ── Step-level error + navigation ───────────────────────────── */}
          {stepError && (
            <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-2.5 text-sm text-destructive">
              {stepError}
            </p>
          )}
          {activeId === "review" && error && (
            <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-2.5 text-sm text-destructive">
              {error}
            </p>
          )}

          <div className="flex gap-3 pt-4 border-t border-border/30">
            {step > 0 && (
              <button
                type="button"
                onClick={goBack}
                className="flex items-center gap-1.5 rounded-xl border border-border/50 px-5 py-3 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              >
                <ChevronLeft className="h-4 w-4" />
                {t("project.wizardBack")}
              </button>
            )}
            {activeId !== "review" ? (
              <button
                type="button"
                onClick={goNext}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-primary px-6 py-3 text-sm font-bold text-primary-foreground btn-shine shadow-lg shadow-primary/15 hover:bg-primary/90 transition-colors"
              >
                {t("project.wizardNext")}
                <ChevronRight className="h-4 w-4" />
              </button>
            ) : (
              <button
                type="submit"
                disabled={loading || !session}
                className="flex-1 rounded-xl bg-primary px-6 py-3 text-sm font-bold text-primary-foreground btn-shine shadow-lg shadow-primary/15 hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
                {loading ? t("project.creating") : t("project.createProject")}
              </button>
            )}
            <button
              type="button"
              onClick={() => router.push("/dashboard")}
              className="rounded-xl border border-border/50 px-5 py-3 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              {t("project.cancel")}
            </button>
          </div>
        </div>

        {/* ── Pinned desktop preview sidebar ─────────────────────────── */}
        {showPreviewPane && (
          <aside className="hidden lg:sticky lg:top-24 lg:block">{previewPane}</aside>
        )}
      </form>
    </div>
  );
}

/* ── Review step helpers ───────────────────────────────────────────────────── */
function ReviewSection({
  title,
  onEdit,
  editLabel,
  children,
}: {
  title: string;
  onEdit: () => void;
  editLabel: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border bg-muted/30 p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-xs font-bold text-foreground uppercase tracking-wide">{title}</p>
        <button
          type="button"
          onClick={onEdit}
          className="text-xs font-medium text-primary hover:underline"
        >
          {editLabel}
        </button>
      </div>
      <div className="flex flex-col gap-1.5">{children}</div>
    </div>
  );
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-foreground text-right">{value}</span>
    </div>
  );
}
