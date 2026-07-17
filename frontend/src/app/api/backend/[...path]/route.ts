import { headers } from "next/headers";
import { type NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { signInternalAuthToken } from "@/lib/internal-auth";
import { forwardableHeaders } from "@/lib/proxy-headers";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

// The Structural tab's design POST rides through this proxy and structapi
// is allowed up to 120 s (structagent_client) plus Cloud Run cold starts —
// Vercel's default function duration killed the request mid-flight with a
// platform 504. Match the agent route's allowance.
export const maxDuration = 300;

type Params = Promise<{ path: string[] }>;

async function proxy(
  req: NextRequest,
  { params }: { params: Params },
  method: string
): Promise<NextResponse> {
  let session = null as Awaited<ReturnType<typeof auth.api.getSession>>;
  try {
    session = await auth.api.getSession({ headers: await headers() });
  } catch (error) {
    console.error("Session retrieval failed:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const secret = process.env.INTERNAL_AUTH_SECRET;
  if (!secret) {
    throw new Error("INTERNAL_AUTH_SECRET is not set");
  }
  const token = await signInternalAuthToken(session.user.id, secret);

  const { path } = await params;
  const search = req.nextUrl.search;
  const targetUrl = `${BACKEND_URL}/api/${path.join("/")}${search}`;

  // For GET/DELETE, skip body handling to avoid issues with bodyless requests
  const body = method === "GET" || method === "DELETE" ? undefined : await req.arrayBuffer();

  let backendResponse: Response;
  try {
    backendResponse = await fetch(targetUrl, {
      method,
      headers: {
        ...forwardableHeaders(req.headers),
        "X-Internal-Auth": token,
      },
      body,
    });
  } catch (error) {
    console.error("Backend request failed:", error);
    return NextResponse.json({ error: "Service unavailable" }, { status: 503 });
  }

  // Use arrayBuffer to preserve binary content (PDF, DXF, etc.)
  const responseBody = await backendResponse.arrayBuffer();
  const contentType = backendResponse.headers.get("content-type") ?? "application/json";
  const contentDisposition = backendResponse.headers.get("content-disposition");
  // Preserve backend caching intent (e.g. no-store on AI render images so a
  // stale image is never shown for changed geometry / another project).
  const cacheControl = backendResponse.headers.get("cache-control");

  return new NextResponse(responseBody, {
    status: backendResponse.status,
    headers: {
      "Content-Type": contentType,
      // Preserve Content-Disposition for file downloads
      ...(contentDisposition && {
        "Content-Disposition": contentDisposition,
      }),
      ...(cacheControl && { "Cache-Control": cacheControl }),
    },
  });
}

export async function GET(req: NextRequest, ctx: { params: Params }) {
  return proxy(req, ctx, "GET");
}

export async function POST(req: NextRequest, ctx: { params: Params }) {
  return proxy(req, ctx, "POST");
}

export async function PUT(req: NextRequest, ctx: { params: Params }) {
  return proxy(req, ctx, "PUT");
}

export async function PATCH(req: NextRequest, ctx: { params: Params }) {
  return proxy(req, ctx, "PATCH");
}

export async function DELETE(req: NextRequest, ctx: { params: Params }) {
  return proxy(req, ctx, "DELETE");
}
