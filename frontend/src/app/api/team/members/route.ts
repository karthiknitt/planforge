import { headers } from "next/headers";
import { NextResponse } from "next/server";
import { auth } from "@/lib/auth";

interface DeleteBody {
  teamId: number;
  targetUserId: string;
}

export async function DELETE(req: Request): Promise<NextResponse> {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = (await req.json()) as DeleteBody;
  const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

  const res = await fetch(`${backendUrl}/api/teams/${body.teamId}/members/${body.targetUserId}`, {
    method: "DELETE",
    headers: { "X-User-Id": session.user.id },
  });

  if (!res.ok) {
    const data = (await res.json()) as { detail?: string };
    return NextResponse.json(
      { error: data.detail ?? "Failed to remove member" },
      { status: res.status }
    );
  }

  return new NextResponse(null, { status: 204 });
}
