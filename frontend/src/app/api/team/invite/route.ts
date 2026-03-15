import { headers } from "next/headers";
import { NextResponse } from "next/server";
import { auth } from "@/lib/auth";

interface InviteBody {
  teamId: number;
  email: string;
  role: string;
}

export async function POST(req: Request): Promise<NextResponse> {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = (await req.json()) as InviteBody;
  const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

  const res = await fetch(`${backendUrl}/api/teams/${body.teamId}/members`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-User-Id": session.user.id,
    },
    body: JSON.stringify({ email: body.email, role: body.role }),
  });

  if (!res.ok) {
    const data = (await res.json()) as { detail?: string };
    return NextResponse.json({ error: data.detail ?? "Failed to invite" }, { status: res.status });
  }

  return NextResponse.json(await res.json());
}
