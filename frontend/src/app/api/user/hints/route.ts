import { eq } from "drizzle-orm";
import { headers } from "next/headers";
import { NextResponse } from "next/server";
import { db } from "@/db";
import { user as userTable } from "@/db/schema";
import { auth } from "@/lib/auth";
import { isHintId, parseDismissedHints } from "@/lib/hint-ids";

// Marks one first-visit hint as dismissed for the current user. Per-feature
// (not a single flag like /api/user/onboarding) — body is { hintId }, and
// the existing dismissed set is read back before writing so dismissing one
// hint never clobbers another dismissed concurrently.
export async function PATCH(req: Request): Promise<NextResponse> {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body: unknown = await req.json().catch(() => null);
  const hintId = (body as { hintId?: unknown } | null)?.hintId;
  if (!isHintId(hintId)) {
    return NextResponse.json({ error: "Invalid hintId" }, { status: 400 });
  }

  const rows = await db
    .select({ dismissedHints: userTable.dismissedHints })
    .from(userTable)
    .where(eq(userTable.id, session.user.id))
    .limit(1);

  const current = parseDismissedHints(rows[0]?.dismissedHints);
  if (!current.includes(hintId)) {
    await db
      .update(userTable)
      .set({ dismissedHints: JSON.stringify([...current, hintId]) })
      .where(eq(userTable.id, session.user.id));
  }

  return new NextResponse(null, { status: 204 });
}
