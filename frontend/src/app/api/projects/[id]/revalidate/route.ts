import { and, eq } from "drizzle-orm";
import { revalidateTag } from "next/cache";
import { headers } from "next/headers";
import { NextResponse } from "next/server";
import { db } from "@/db";
import { project as projectTable, teamMember } from "@/db/schema";
import { auth } from "@/lib/auth";

// Busts the cached layout payload for a project after an edit is persisted,
// so a page reload shows the saved geometry instead of a up-to-5-min-stale
// pre-edit cache entry.
export async function POST(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const { id } = await params;

  // Owner OR team member — any authed user could previously bust any
  // project's cache tag (cross-tenant invalidation primitive).
  const rows = await db
    .select({ userId: projectTable.userId, teamId: projectTable.teamId })
    .from(projectTable)
    .where(eq(projectTable.id, id))
    .limit(1);
  const proj = rows[0];
  if (!proj) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  let canAccess = proj.userId === session.user.id;
  if (!canAccess && proj.teamId != null) {
    const membership = await db
      .select({ id: teamMember.id })
      .from(teamMember)
      .where(and(eq(teamMember.teamId, proj.teamId), eq(teamMember.userId, session.user.id)))
      .limit(1);
    canAccess = membership.length > 0;
  }
  if (!canAccess) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  revalidateTag(`project-${id}`, "max");
  return NextResponse.json({ ok: true });
}
