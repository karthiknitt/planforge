"use client";

import { Minus, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { useSession } from "@/lib/auth-client";
import { CITIES, type CustomRoomSpec, MUNICIPALITIES, ROOM_TYPES } from "@/lib/layout-types";
import { useLocale } from "@/lib/locale-context";

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
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-xs font-bold text-primary ring-1 ring-primary/15">
        {num}
      </span>
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
  const [loading, setLoading] = useState(false);
  const [configMode, setConfigMode] = useState<"basic" | "advanced">("basic");
  const [customRooms, setCustomRooms] = useState<CustomRoomSpec[]>([]);
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
    <div className="mx-auto max-w-3xl px-4 sm:px-6 py-10 sm:py-14">
      <div className="mb-10">
        <h1
          className="text-2xl sm:text-3xl font-black text-foreground mb-2"
          style={{ fontFamily: "var(--font-display)" }}
        >
          {t("project.newProject")}
        </h1>
        <p className="text-sm text-muted-foreground/60">{t("project.newProjectHint")}</p>
      </div>

      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-10 md:rounded-2xl md:border md:border-border/40 md:bg-card/20 md:p-8 lg:p-10"
      >
        {/* ── 1. Project name ───────────────────────────────────────── */}
        <div className="flex flex-col gap-4">
          <Section num="1" title={t("project.newProject")} />
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

        {/* ── 2. Plot & city ────────────────────────────────────────── */}
        <div className="flex flex-col gap-4">
          <Section num="2" title={t("project.plotDimensions")} />

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
                  { value: "l_shaped", label: "L-Shaped", desc: "Rectangle with corner cutout" },
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
                  <span className="block text-xs text-muted-foreground mt-0.5">{opt.desc}</span>
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
                An L-shaped plot is a rectangle with one corner cut out. Enter overall dimensions
                above, then specify the corner and size of the cutout below.
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
                  <p className="text-xs text-muted-foreground">Must be less than plot width</p>
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
                  <p className="text-xs text-muted-foreground">Must be less than plot length</p>
                </div>
              </div>
            </div>
          )}

          {form.plot_shape === "quadrilateral" && (
            <div className="rounded-lg border bg-muted/30 p-4 flex flex-col gap-3">
              <p className="text-xs text-muted-foreground">{t("project.quadHint")}</p>
              {(
                [
                  t("project.frontLeft"),
                  t("project.frontRight"),
                  t("project.rearRight"),
                  t("project.rearLeft"),
                ] as const
              ).map((label, idx) => (
                <div key={label} className="grid grid-cols-[140px_1fr_1fr] items-center gap-3">
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
            <Label htmlFor="municipality">{t("project.municipality")}</Label>
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

        {/* ── 3. Orientation & setbacks ──────────────────────────────── */}
        <div className="flex flex-col gap-4">
          <Section num="3" title={t("project.orientationSetbacks")} />
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
            <p className="text-xs font-medium text-muted-foreground mb-3 uppercase tracking-wide">
              {t("project.setbacks")}
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
          <Section num="4" title={t("project.floorConfiguration")} />

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
                <Label htmlFor="has_stilt" className="cursor-pointer font-normal">
                  {t("project.stiltFloor")}
                </Label>
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
        </div>

        {/* ── 5. Room configuration ─────────────────────────────────── */}
        <div className="flex flex-col gap-4">
          <Section num="5" title={t("project.roomConfiguration")} />

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

        {/* ── Submit ────────────────────────────────────────────────── */}
        {error && (
          <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-2.5 text-sm text-destructive">
            {error}
          </p>
        )}

        <div className="flex gap-3 pt-4 border-t border-border/30">
          <button
            type="submit"
            disabled={loading || !session}
            className="flex-1 rounded-xl bg-primary px-6 py-3 text-sm font-bold text-primary-foreground btn-shine shadow-lg shadow-primary/15 hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {loading ? t("project.creating") : t("project.createProject")}
          </button>
          <button
            type="button"
            onClick={() => router.push("/dashboard")}
            className="rounded-xl border border-border/50 px-5 py-3 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            {t("project.cancel")}
          </button>
        </div>
      </form>
    </div>
  );
}
