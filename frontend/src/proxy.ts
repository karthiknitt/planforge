import { type NextRequest, NextResponse } from "next/server";

// Routes that require an authenticated session
const PROTECTED_PATHS = ["/dashboard", "/projects", "/account"];
// Routes that authenticated users should be redirected away from
const AUTH_PATHS = ["/sign-in", "/sign-up"];
const SESSION_COOKIE = "better-auth.session_token";

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = request.cookies.has(SESSION_COOKIE);

  // Authenticated users hitting /sign-in or /sign-up → send to dashboard
  if (hasSession && AUTH_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  // Unauthenticated users hitting protected app routes → send to sign-in
  if (!hasSession && PROTECTED_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.redirect(new URL("/sign-in", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all paths except:
     * - /api/auth/* (Better Auth handler)
     * - /_next/* (Next.js internals)
     * - /favicon.ico, static files
     */
    "/((?!api/auth|_next/static|_next/image|favicon.ico).*)",
  ],
};
