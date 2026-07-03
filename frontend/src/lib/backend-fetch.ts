import { signInternalAuthToken } from "@/lib/internal-auth";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function fetchBackend(
  userId: string,
  path: string,
  init?: RequestInit
): Promise<Response> {
  const secret = process.env.INTERNAL_AUTH_SECRET;
  if (!secret) {
    throw new Error("INTERNAL_AUTH_SECRET is not set");
  }
  const token = await signInternalAuthToken(userId, secret);
  // Normalize via Headers() first — init.headers may legitimately be a plain
  // object, a Headers instance, or a [string, string][] tuple array, and
  // object-spreading only handles the first of those correctly.
  const headers = new Headers(init?.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("X-Internal-Auth", token);

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15_000);
  try {
    return await fetch(`${BACKEND_URL}/api/${path.replace(/^\//, "")}`, {
      ...init,
      headers,
      signal: init?.signal ?? controller.signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }
}
