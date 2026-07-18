import { and, eq } from "drizzle-orm";
import { headers } from "next/headers";
import { notFound, redirect } from "next/navigation";

import { db } from "@/db";
import { project as projectTable, teamMember } from "@/db/schema";
import { auth } from "@/lib/auth";
import { EditProjectForm } from "./edit-form";

export default async function EditProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/sign-in");

  const rows = await db.select().from(projectTable).where(eq(projectTable.id, id)).limit(1);
  const project = rows[0];

  if (!project) notFound();

  let canAccess = project.userId === session.user.id;
  if (!canAccess && project.teamId != null) {
    const membership = await db
      .select({ id: teamMember.id })
      .from(teamMember)
      .where(and(eq(teamMember.teamId, project.teamId), eq(teamMember.userId, session.user.id)))
      .limit(1);
    canAccess = membership.length > 0;
  }
  if (!canAccess) notFound();

  return (
    <EditProjectForm
      project={{
        id: project.id,
        name: project.name,
        plotLength: project.plotLength,
        plotWidth: project.plotWidth,
        setbackFront: project.setbackFront,
        setbackRear: project.setbackRear,
        setbackLeft: project.setbackLeft,
        setbackRight: project.setbackRight,
        roadSide: project.roadSide,
        numBedrooms: project.numBedrooms,
        toilets: project.toilets,
        parking: project.parking,
        city: project.city,
        roadWidthM: project.roadWidthM,
        hasPooja: project.hasPooja,
        hasStudy: project.hasStudy,
        hasBalcony: project.hasBalcony,
        plotShape: project.plotShape,
        plotFrontWidth: project.plotFrontWidth,
        plotRearWidth: project.plotRearWidth,
        plotSideOffset: project.plotSideOffset,
        numFloors: project.numFloors,
        hasStilt: project.hasStilt,
        hasBasement: project.hasBasement,
        vastuEnabled: project.vastuEnabled,
      }}
    />
  );
}
