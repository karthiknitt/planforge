import { eq } from "drizzle-orm";
import { headers } from "next/headers";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { db } from "@/db";
import { project as projectTable } from "@/db/schema";
import { auth } from "@/lib/auth";
import type { GenerateResponse } from "@/lib/layout-types";
import { Button } from "@/components/ui/button";
import { LayoutViewer } from "./layout-viewer";

async function fetchLayouts(
  projectId: string,
  userId: string
): Promise<GenerateResponse | null> {
  try {
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/generate`,
      { headers: { "X-User-Id": userId }, cache: "no-store" }
    );
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function ProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/sign-in");

  const rows = await db
    .select()
    .from(projectTable)
    .where(eq(projectTable.id, id))
    .limit(1);
  const project = rows[0];

  if (!project || project.userId !== session.user.id) notFound();

  const generateData = await fetchLayouts(id, session.user.id);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-3">
          <Button variant="ghost" size="sm" asChild>
            <Link href="/dashboard">← Dashboard</Link>
          </Button>
          <span className="text-muted-foreground">/</span>
          <span className="font-semibold">{project.name}</span>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-4 py-10">
        {/* Project summary strip */}
        <div className="flex flex-wrap gap-6 rounded-xl border bg-muted/40 px-5 py-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Plot size
            </p>
            <p className="mt-0.5 font-medium">
              {project.plotLength} m × {project.plotWidth} m
            </p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Configuration
            </p>
            <p className="mt-0.5 font-medium">
              {project.bhk} BHK · {project.toilets} Toilet
              {project.toilets > 1 ? "s" : ""}
              {project.parking ? " · Parking" : ""}
            </p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Orientation
            </p>
            <p className="mt-0.5 font-medium">
              Road: {project.roadSide} · North: {project.northDirection}
            </p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Setbacks (m)
            </p>
            <p className="mt-0.5 font-medium text-sm">
              F {project.setbackFront} · Rear {project.setbackRear} · L{" "}
              {project.setbackLeft} · R {project.setbackRight}
            </p>
          </div>
        </div>

        {/* Layout viewer */}
        <LayoutViewer
          generateData={generateData}
          plotWidth={parseFloat(project.plotWidth)}
          plotLength={parseFloat(project.plotLength)}
          roadSide={project.roadSide}
          northDirection={project.northDirection}
        />
      </main>
    </div>
  );
}
