import { eq } from "drizzle-orm";
import { headers } from "next/headers";
import { notFound, redirect } from "next/navigation";

import { db } from "@/db";
import { project as projectTable } from "@/db/schema";
import { auth } from "@/lib/auth";
import { EditProjectForm } from "./edit-form";

export default async function EditProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/sign-in");

  const rows = await db.select().from(projectTable).where(eq(projectTable.id, id)).limit(1);
  const project = rows[0];

  if (!project || project.userId !== session.user.id) notFound();

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
        bhk: project.bhk,
        toilets: project.toilets,
        parking: project.parking,
      }}
    />
  );
}
