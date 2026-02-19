import { eq } from "drizzle-orm";
import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
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

  const generateData = await fetchLayouts(id, session.user.id);

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
      {/* Project summary strip */}
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

      {/* Layout viewer */}
      <LayoutViewer
        generateData={generateData}
        plotWidth={parseFloat(project.plotWidth)}
        plotLength={parseFloat(project.plotLength)}
        roadSide={project.roadSide}
        northDirection={project.northDirection}
        projectId={id}
        planTier={planTier}
        plotShape={project.plotShape}
        plotFrontWidth={project.plotFrontWidth ? parseFloat(project.plotFrontWidth) : undefined}
        plotRearWidth={project.plotRearWidth ? parseFloat(project.plotRearWidth) : undefined}
      />
    </main>
  );
}
