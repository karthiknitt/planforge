import { and, eq } from "drizzle-orm";
import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { Suspense } from "react";
import { Button } from "@/components/ui/button";
import { db } from "@/db";
import { project as projectTable, teamMember, user as userTable } from "@/db/schema";
import { auth } from "@/lib/auth";
import type { HintId } from "@/lib/hint-ids";
import { parseDismissedHints } from "@/lib/hint-ids";
import { fetchLayouts } from "./fetch-layouts";
import { GeneratingFallback } from "./generating-fallback";
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

// ── Streaming layout section ────────────────────────────────────────────────

interface LayoutSectionProps {
  projectId: string;
  userId: string;
  projectName: string;
  plotXExtent: number;
  plotYExtent: number;
  roadSide: string;
  northDirection: string;
  planTier: string;
  plotShape?: string;
  plotFrontWidth?: number;
  plotRearWidth?: number;
  plotCorners?: [number, number][];
  cutoutCorner?: string;
  cutoutWidth?: number;
  cutoutHeight?: number;
  vastuEnabled?: boolean;
  municipality?: string | null;
  shareToken?: string | null;
  approvalStatus?: string | null;
  approvalNote?: string | null;
  approvalUpdatedAt?: Date | null;
  dismissedHints: HintId[];
}

async function LayoutSection({
  projectId,
  userId,
  projectName,
  plotXExtent,
  plotYExtent,
  roadSide,
  northDirection,
  planTier,
  plotShape,
  plotFrontWidth,
  plotRearWidth,
  plotCorners,
  cutoutCorner,
  cutoutWidth,
  cutoutHeight,
  vastuEnabled,
  municipality,
  shareToken,
  approvalStatus,
  approvalNote,
  approvalUpdatedAt,
  dismissedHints,
}: LayoutSectionProps) {
  const generateData = await fetchLayouts(projectId, userId);
  return (
    <LayoutViewer
      generateData={generateData}
      dismissedHints={dismissedHints}
      plotXExtent={plotXExtent}
      plotYExtent={plotYExtent}
      roadSide={roadSide}
      northDirection={northDirection}
      projectId={projectId}
      projectName={projectName}
      planTier={planTier}
      plotShape={plotShape}
      plotFrontWidth={plotFrontWidth}
      plotRearWidth={plotRearWidth}
      plotCorners={plotCorners}
      cutoutCorner={cutoutCorner}
      cutoutWidth={cutoutWidth}
      cutoutHeight={cutoutHeight}
      vastuEnabled={vastuEnabled}
      municipality={municipality}
      shareToken={shareToken}
      initialApproval={{
        status: approvalStatus as "approved" | "changes_requested" | "pending" | null,
        note: approvalNote ?? null,
        updatedAt: approvalUpdatedAt ? approvalUpdatedAt.toISOString() : null,
      }}
    />
  );
}

// ── Page ────────────────────────────────────────────────────────────────────

export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  // Session read depends only on request headers, the project row select only
  // on the route's `id` param — no data dependency between them, so run concurrently.
  const requestHeaders = await headers();
  const [session, rows] = await Promise.all([
    auth.api.getSession({ headers: requestHeaders }),
    db.select().from(projectTable).where(eq(projectTable.id, id)).limit(1),
  ]);
  if (!session) redirect("/sign-in");

  const project = rows[0];
  if (!project) notFound();

  // Owner OR member of the project's team — matches the backend access rule
  let canAccess = project.userId === session.user.id;
  // Plan-tier only depends on session.user.id, not on canAccess, so it can run
  // alongside the membership check — a small latency win on the common
  // (authorized) path, at the cost of one wasted read-only query on the rare
  // unauthorized path (which hits notFound() below and discards it).
  const [membership, userRows] = await Promise.all([
    !canAccess && project.teamId != null
      ? db
          .select({ id: teamMember.id })
          .from(teamMember)
          .where(and(eq(teamMember.teamId, project.teamId), eq(teamMember.userId, session.user.id)))
          .limit(1)
      : Promise.resolve([]),
    db
      .select({ planTier: userTable.planTier, dismissedHints: userTable.dismissedHints })
      .from(userTable)
      .where(eq(userTable.id, session.user.id))
      .limit(1),
  ]);
  if (!canAccess) canAccess = membership.length > 0;
  if (!canAccess) notFound();

  const planTier = userRows[0]?.planTier ?? "free";
  const dismissedHints = parseDismissedHints(userRows[0]?.dismissedHints);

  const lengthFt = metresToFeet(project.plotLength);
  const widthFt = metresToFeet(project.plotWidth);

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-5 md:py-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm min-w-0">
        <Button variant="ghost" size="sm" asChild className="-ml-2 shrink-0">
          <Link href="/dashboard">← Dashboard</Link>
        </Button>
        <span className="text-muted-foreground shrink-0">/</span>
        <h1 className="font-semibold truncate min-w-0">{project.name}</h1>
        <Button variant="outline" size="sm" asChild className="ml-auto shrink-0">
          <Link href={`/projects/${id}/edit`}>Edit</Link>
        </Button>
      </div>

      {/* Project summary strip — renders immediately from DB */}
      <div className="grid grid-cols-2 sm:flex sm:flex-wrap gap-3 sm:gap-6 rounded-xl border bg-muted/40 px-4 sm:px-5 py-3 sm:py-4">
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
          <p className="mt-0.5 font-medium capitalize">
            {project.municipality ?? project.city ?? "NBC Defaults"}
          </p>
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
          projectName={project.name}
          plotXExtent={parseFloat(project.plotWidth)}
          plotYExtent={parseFloat(project.plotLength)}
          roadSide={project.roadSide}
          northDirection={project.northDirection}
          planTier={planTier}
          plotShape={project.plotShape}
          plotFrontWidth={project.plotFrontWidth ? parseFloat(project.plotFrontWidth) : undefined}
          plotRearWidth={project.plotRearWidth ? parseFloat(project.plotRearWidth) : undefined}
          plotCorners={
            project.plotCorners
              ? (JSON.parse(project.plotCorners) as [number, number][])
              : undefined
          }
          cutoutCorner={project.cutoutCorner ?? undefined}
          cutoutWidth={project.cutoutWidth ? parseFloat(String(project.cutoutWidth)) : undefined}
          cutoutHeight={project.cutoutHeight ? parseFloat(String(project.cutoutHeight)) : undefined}
          vastuEnabled={project.vastuEnabled}
          municipality={project.municipality}
          shareToken={project.shareToken}
          approvalStatus={project.approvalStatus}
          approvalNote={project.approvalNote}
          approvalUpdatedAt={project.approvalUpdatedAt}
          dismissedHints={dismissedHints}
        />
      </Suspense>
    </div>
  );
}
