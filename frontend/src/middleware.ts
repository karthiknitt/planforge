import { type NextRequest, NextResponse } from "next/server";

const PROTECTED_PATHS = ["/dashboard", "/projects", "/account"];
const AUTH_PATHS = ["/sign-in", "/sign-up"];

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const isProtected = PROTECTED_PATHS.some((p) => pathname.startsWith(p));
  const isAuthPath = AUTH_PATHS.some((p) => pathname.startsWith(p));

  // Skip everything that isn't a protected or auth route
  if (!isProtected && !isAuthPath) {
    return NextResponse.next();
  }

  // Validate the session via Better Auth's own endpoint.
  // This handles expired/stale cookies correctly — unlike a bare cookie presence check.
  let hasValidSession = false;
  try {
    const res = await fetch(
      new URL("/api/auth/get-session", request.nextUrl.origin).toString(),
      {
        headers: { cookie: request.headers.get("cookie") ?? "" },
        // Don't cache — always get fresh session state
        cache: "no-store",
      }
    );
    if (res.ok) {
      const data = await res.json();
      hasValidSession = data != null && data?.user != null;
    }
  } catch {
    // Network/parse error — treat as unauthenticated (fail open for UX)
  }

  // Authenticated user visiting /sign-in or /sign-up → send to dashboard
  if (hasValidSession && isAuthPath) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  // Unauthenticated user visiting a protected route → send to sign-in
  if (!hasValidSession && isProtected) {
    return NextResponse.redirect(new URL("/sign-in", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all paths except:
     * - /api/auth/* (Better Auth handler — must be excluded to avoid infinite loop)
     * - /_next/* (Next.js internals)
     * - Static files
     */
    "/((?!api/auth|_next/static|_next/image|favicon.ico).*)",
  ],
};
