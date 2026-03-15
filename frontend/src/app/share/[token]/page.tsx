import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { FloorPlanSVG } from "@/components/floor-plan-svg";
import { SectionViewSVG } from "@/components/section-view-svg";
import type { FloorPlanData, GenerateResponse, LayoutData } from "@/lib/layout-types";

// ── Types returned by the backend share endpoint ─────────────────────────────

interface ShareProjectInfo {
  id: string;
  name: string;
  plot_length: number;
  plot_width: number;
  road_side: string;
  north_direction: string;
  num_bedrooms: number;
  toilets: number;
  parking: boolean;
  plot_shape: string;
}

interface ShareApiResponse {
  project: ShareProjectInfo;
  generate: GenerateResponse;
}

// ── Fetch helper ──────────────────────────────────────────────────────────────

async function fetchSharedProject(token: string): Promise<ShareApiResponse | null> {
  try {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/share/${token}`, {
      next: { revalidate: 60 },
    });
    if (res.status === 404) return null;
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

// ── Metadata ──────────────────────────────────────────────────────────────────

export async function generateMetadata({
  params,
}: {
  params: Promise<{ token: string }>;
}): Promise<Metadata> {
  const { token } = await params;
  const data = await fetchSharedProject(token);
  const name = data?.project.name ?? "Shared Floor Plan";
  return {
    title: `${name} — PlanForge`,
    description: "View this residential floor plan shared via PlanForge.",
  };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function metresToFeet(metres: number): string {
  return (Math.round((metres / 0.3048) * 10) / 10).toFixed(1);
}

const TYPE_LABELS: Record<string, string> = {
  living: "Living / Hall",
  bedroom: "Bedroom",
  master_bedroom: "Master Bedroom",
  kitchen: "Kitchen",
  toilet: "Toilet",
  staircase: "Staircase",
  parking: "Parking",
  utility: "Utility / Other",
  pooja: "Pooja Room",
  study: "Study",
  balcony: "Balcony",
  dining: "Dining",
  servant_quarter: "Servant Quarter",
  home_office: "Home Office",
  gym: "Gym",
  store_room: "Store Room",
  garage: "Garage",
  passage: "Passage",
};

const SWATCH: Record<string, string> = {
  living: "bg-yellow-100 border-yellow-400",
  bedroom: "bg-violet-100 border-violet-500",
  master_bedroom: "bg-purple-100 border-purple-500",
  kitchen: "bg-green-100 border-green-600",
  toilet: "bg-sky-100 border-sky-500",
  staircase: "bg-slate-100 border-slate-400",
  parking: "bg-slate-50 border-slate-300",
  utility: "bg-slate-50 border-slate-300",
  pooja: "bg-orange-50 border-orange-400",
  study: "bg-emerald-50 border-emerald-500",
  balcony: "bg-blue-50 border-blue-400",
  dining: "bg-yellow-50 border-yellow-500",
  servant_quarter: "bg-orange-50 border-orange-500",
  home_office: "bg-green-50 border-green-500",
  gym: "bg-red-50 border-red-400",
  store_room: "bg-slate-50 border-slate-400",
  garage: "bg-blue-50 border-blue-500",
  passage: "bg-slate-100 border-slate-400",
};

// ── Read-only layout viewer (server-compatible, no interactivity) ─────────────

function ReadOnlyLayoutCard({
  layout,
  plotWidth,
  plotLength,
  roadSide,
}: {
  layout: LayoutData;
  plotWidth: number;
  plotLength: number;
  roadSide: string;
}) {
  const groundFloor: FloorPlanData = layout.ground_floor;
  const firstFloor: FloorPlanData = layout.first_floor;
  const presentGround = [...new Set(groundFloor.rooms.map((r) => r.type))];
  const presentFirst = [...new Set(firstFloor.rooms.map((r) => r.type))];
  const allTypes = [...new Set([...presentGround, ...presentFirst])];

  return (
    <div className="rounded-2xl border border-border bg-card p-5 flex flex-col gap-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-foreground">
            Layout {layout.id} — {layout.name}
          </h3>
          {layout.score && (
            <p className="text-xs text-muted-foreground mt-0.5">
              Score: {layout.score.total.toFixed(0)}/100 · Light{" "}
              {layout.score.natural_light.toFixed(0)} · Adjacency{" "}
              {layout.score.adjacency.toFixed(0)}
            </p>
          )}
        </div>
        <span
          className={[
            "rounded-md border px-2 py-0.5 text-xs font-semibold",
            layout.compliance.passed
              ? "border-green-500/40 bg-green-500/10 text-green-700"
              : "border-red-500/40 bg-red-500/10 text-red-700",
          ].join(" ")}
        >
          {layout.compliance.passed ? "Compliant" : "Non-compliant"}
        </span>
      </div>

      {/* Compliance violations */}
      {layout.compliance.violations.length > 0 && (
        <ul className="list-inside list-disc space-y-0.5 text-sm text-red-600">
          {layout.compliance.violations.map((v) => (
            <li key={v}>{v}</li>
          ))}
        </ul>
      )}

      {/* Floor plans side by side */}
      <div className="flex flex-col gap-4 sm:flex-row sm:gap-6">
        <div className="flex flex-col gap-2 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Ground Floor
          </p>
          <FloorPlanSVG
            floorPlan={groundFloor}
            plotWidth={plotWidth}
            plotLength={plotLength}
            roadSide={roadSide}
            className="rounded-xl border w-full"
          />
        </div>
        <div className="flex flex-col gap-2 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            First Floor
          </p>
          <FloorPlanSVG
            floorPlan={firstFloor}
            plotWidth={plotWidth}
            plotLength={plotLength}
            roadSide={roadSide}
            className="rounded-xl border w-full"
          />
        </div>
      </div>

      {/* Section view */}
      <div className="flex flex-col gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Section View
        </p>
        <SectionViewSVG buildingWidth={plotWidth} className="rounded-xl border w-full max-w-xl" />
      </div>

      {/* Room legend */}
      <div className="flex flex-wrap gap-3">
        {allTypes.map((type) => (
          <div key={type} className="flex items-center gap-1.5">
            <div
              className={["size-3 rounded-sm border", SWATCH[type] ?? SWATCH.utility].join(" ")}
            />
            <span className="text-xs text-muted-foreground">{TYPE_LABELS[type] ?? type}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default async function SharePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const data = await fetchSharedProject(token);

  if (!data) notFound();

  const { project, generate } = data;
  const lengthFt = metresToFeet(project.plot_length);
  const widthFt = metresToFeet(project.plot_width);

  return (
    <div className="min-h-screen bg-background">
      {/* Top bar */}
      <header className="border-b border-border bg-card px-4 py-3 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 text-sm font-semibold">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-blue-700 text-white text-xs font-bold">
            P
          </span>
          <span>
            Plan<span className="text-orange-500">Forge</span>
          </span>
        </Link>
        <span className="rounded-md border border-border bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          Read-only view
        </span>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-8 flex flex-col gap-8">
        {/* Project summary */}
        <div className="flex flex-col gap-2">
          <h1 className="text-2xl font-bold text-foreground">{project.name}</h1>
          <div className="flex flex-wrap gap-4 rounded-xl border bg-muted/40 px-5 py-4 text-sm">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Plot size
              </p>
              <p className="mt-0.5 font-medium">
                {lengthFt} × {widthFt} ft
              </p>
              <p className="text-xs text-muted-foreground">
                ({project.plot_length} × {project.plot_width} m)
              </p>
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Configuration
              </p>
              <p className="mt-0.5 font-medium">
                {project.num_bedrooms} BHK · {project.toilets} Toilet
                {project.toilets > 1 ? "s" : ""}
                {project.parking ? " · Parking" : ""}
              </p>
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Orientation
              </p>
              <p className="mt-0.5 font-medium">Road faces {project.road_side}</p>
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Layouts
              </p>
              <p className="mt-0.5 font-medium">{generate.layouts.length} options</p>
            </div>
          </div>
        </div>

        {/* Layout cards */}
        <div className="flex flex-col gap-6">
          {generate.layouts.map((layout) => (
            <ReadOnlyLayoutCard
              key={layout.id}
              layout={layout}
              plotWidth={project.plot_width}
              plotLength={project.plot_length}
              roadSide={project.road_side}
            />
          ))}
        </div>

        {/* Standard details */}
        <div className="rounded-lg border border-border bg-muted/40 px-4 py-3 text-xs text-muted-foreground grid grid-cols-2 gap-1 sm:grid-cols-3">
          <span>Floor height: 3.0 m (each floor)</span>
          <span>Slab thickness: 150 mm (RCC)</span>
          <span>Parapet: 1.0 m above roof</span>
          <span>External wall: 230 mm brick</span>
          <span>Foundation: 600 mm below GL</span>
          <span>Scale: 1:100</span>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border py-6 text-center text-xs text-muted-foreground">
        <p>
          Floor plan generated by{" "}
          <Link href="/" className="font-medium text-foreground hover:underline">
            PlanForge
          </Link>{" "}
          — G+1 residential floor plan generator for Indian builders
        </p>
      </footer>
    </div>
  );
}
