import { eq } from "drizzle-orm";
import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { Suspense } from "react";
import { Button } from "@/components/ui/button";
import { db } from "@/db";
import { project as projectTable, user as userTable } from "@/db/schema";
import { auth } from "@/lib/auth";
import type { GenerateResponse } from "@/lib/layout-types";
import { LayoutViewer } from "./layout-viewer";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const rows = await db
    .select({ name: projectTable.name })
    .from(projectTable)
    .where(eq(projectTable.id, id))
    .limit(1);
  const name = rows[0]?.name ?? "Project";
  return { title: name };
}

function metresToFeet(metres: string | number): string {
  return (Math.round((parseFloat(String(metres)) / 0.3048) * 10) / 10).toFixed(1);
}

async function fetchLayouts(projectId: string, userId: string): Promise<GenerateResponse | null> {
  try {
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/generate`,
      {
        headers: { "X-User-Id": userId },
        next: { revalidate: 300, tags: [`project-${projectId}`] },
      }
    );
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

// ── Streaming layout section ────────────────────────────────────────────────

interface LayoutSectionProps {
  projectId: string;
  userId: string;
  plotWidth: number;
  plotLength: number;
  roadSide: string;
  northDirection: string;
  planTier: string;
  plotShape?: string;
  plotFrontWidth?: number;
  plotRearWidth?: number;
}

async function LayoutSection({
  projectId,
  userId,
  plotWidth,
  plotLength,
  roadSide,
  northDirection,
  planTier,
  plotShape,
  plotFrontWidth,
  plotRearWidth,
}: LayoutSectionProps) {
  const generateData = await fetchLayouts(projectId, userId);
  return (
    <LayoutViewer
      generateData={generateData}
      plotWidth={plotWidth}
      plotLength={plotLength}
      roadSide={roadSide}
      northDirection={northDirection}
      projectId={projectId}
      planTier={planTier}
      plotShape={plotShape}
      plotFrontWidth={plotFrontWidth}
      plotRearWidth={plotRearWidth}
    />
  );
}

// ── Generating fallback (shown while solver runs) ───────────────────────────

function GeneratingFallback() {
  const steps = [
    { label: "Solving layout constraints", detail: "CP-SAT solver · 3 variants" },
    { label: "Scoring layouts", detail: "Light · Adjacency · Vastu" },
    { label: "Checking compliance", detail: "NBC / local rules" },
  ];

  return (
    <div className="flex flex-col gap-6 rounded-2xl border border-dashed border-border bg-muted/20 px-8 py-10">
      {/* Progress bar */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between text-sm">
          <span className="font-medium text-foreground">Generating floor plans…</span>
          <span className="text-xs text-muted-foreground animate-pulse">Running</span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-primary"
            style={{
              width: "60%",
              animation: "progress-indeterminate 1.8s ease-in-out infinite",
            }}
          />
        </div>
      </div>

      {/* Step indicators */}
      <div className="flex flex-col gap-3">
        {steps.map((step, i) => (
          <div key={step.label} className="flex items-center gap-3">
            <div
              className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border"
              style={{
                borderColor: "var(--primary)",
                animation: `pulse-step 1.8s ease-in-out ${i * 0.4}s infinite`,
              }}
            >
              <div className="h-2 w-2 rounded-full bg-primary" />
            </div>
            <div>
              <p className="text-sm font-medium text-foreground">{step.label}</p>
              <p className="text-xs text-muted-foreground">{step.detail}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Skeleton cards for layout buttons */}
      <div className="flex gap-3 pt-2">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-9 w-32 animate-pulse rounded-lg bg-muted" />
        ))}
      </div>

      {/* SVG area skeleton */}
      <div className="h-72 animate-pulse rounded-xl bg-muted/60" />

      <style>{`
        @keyframes progress-indeterminate {
          0%   { transform: translateX(-100%); width: 50%; }
          50%  { transform: translateX(50%);   width: 60%; }
          100% { transform: translateX(200%);  width: 50%; }
        }
        @keyframes pulse-step {
          0%, 100% { opacity: 0.4; }
          50%       { opacity: 1; }
        }
      `}</style>
    </div>
  );
}

// ── Page ────────────────────────────────────────────────────────────────────

export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/sign-in");

  const rows = await db.select().from(projectTable).where(eq(projectTable.id, id)).limit(1);
  const project = rows[0];

  if (!project || project.userId !== session.user.id) notFound();

  const userRows = await db
    .select({ planTier: userTable.planTier })
    .from(userTable)
    .where(eq(userTable.id, session.user.id))
    .limit(1);
  const planTier = userRows[0]?.planTier ?? "free";

  const lengthFt = metresToFeet(project.plotLength);
  const widthFt = metresToFeet(project.plotWidth);

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-4 py-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm">
        <Button variant="ghost" size="sm" asChild className="-ml-2">
          <Link href="/dashboard">← Dashboard</Link>
        </Button>
        <span className="text-muted-foreground">/</span>
        <span className="font-semibold truncate">{project.name}</span>
        <Button variant="outline" size="sm" asChild className="ml-auto">
          <Link href={`/projects/${id}/edit`}>Edit project</Link>
        </Button>
      </div>

      {/* Project summary strip — renders immediately from DB */}
      <div className="flex flex-wrap gap-6 rounded-xl border bg-muted/40 px-5 py-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Plot size{project.plotShape === "trapezoid" ? " (Trapezoid)" : ""}
          </p>
          {project.plotShape === "trapezoid" && project.plotFrontWidth && project.plotRearWidth ? (
            <p className="mt-0.5 font-medium">
              {lengthFt} ft deep · Front {metresToFeet(project.plotFrontWidth)} ft · Rear{" "}
              {metresToFeet(project.plotRearWidth)} ft
            </p>
          ) : (
            <>
              <p className="mt-0.5 font-medium">
                {lengthFt} × {widthFt} ft
              </p>
              <p className="text-xs text-muted-foreground">
                ({project.plotLength} × {project.plotWidth} m)
              </p>
            </>
          )}
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Configuration
          </p>
          <p className="mt-0.5 font-medium">
            {project.numBedrooms} BHK · {project.toilets} Toilet{project.toilets > 1 ? "s" : ""}
            {project.parking ? " · Parking" : ""}
          </p>
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            City / Rules
          </p>
          <p className="mt-0.5 font-medium capitalize">{project.city ?? "NBC Defaults"}</p>
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Orientation
          </p>
          <p className="mt-0.5 font-medium">Road faces {project.roadSide}</p>
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Setbacks (ft)
          </p>
          <p className="mt-0.5 text-sm font-medium">
            F {metresToFeet(project.setbackFront)} · Rear {metresToFeet(project.setbackRear)} · L{" "}
            {metresToFeet(project.setbackLeft)} · R {metresToFeet(project.setbackRight)}
          </p>
        </div>
        {(project.hasPooja || project.hasStudy || project.hasBalcony) && (
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Optional rooms
            </p>
            <p className="mt-0.5 text-sm font-medium">
              {[
                project.hasPooja && "Pooja",
                project.hasStudy && "Study",
                project.hasBalcony && "Balcony",
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </div>
        )}
      </div>

      {/* Layout viewer — streams in when solver completes */}
      <Suspense fallback={<GeneratingFallback />}>
        <LayoutSection
          projectId={id}
          userId={session.user.id}
          plotWidth={parseFloat(project.plotWidth)}
          plotLength={parseFloat(project.plotLength)}
          roadSide={project.roadSide}
          northDirection={project.northDirection}
          planTier={planTier}
          plotShape={project.plotShape}
          plotFrontWidth={project.plotFrontWidth ? parseFloat(project.plotFrontWidth) : undefined}
          plotRearWidth={project.plotRearWidth ? parseFloat(project.plotRearWidth) : undefined}
        />
      </Suspense>
    </main>
  );
}
