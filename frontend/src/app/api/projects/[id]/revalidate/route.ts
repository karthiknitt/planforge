import { revalidateTag } from "next/cache";
import { headers } from "next/headers";
import { NextResponse } from "next/server";
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
  revalidateTag(`project-${id}`, "max");
  return NextResponse.json({ ok: true });
}
