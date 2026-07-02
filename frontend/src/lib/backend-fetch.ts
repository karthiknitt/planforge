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
  return fetch(`${BACKEND_URL}/api/${path.replace(/^\//, "")}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers as Record<string, string> | undefined),
      "X-Internal-Auth": token,
    },
  });
}
