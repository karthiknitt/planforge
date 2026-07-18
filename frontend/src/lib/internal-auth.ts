import { SignJWT } from "jose";

export async function signInternalAuthToken(
  userId: string,
  secret: string,
  email?: string
): Promise<string> {
  if (!secret) {
    throw new Error("signInternalAuthToken: secret must not be empty");
  }
  const claims: Record<string, string> = { user_id: userId };
  if (email) {
    claims.email = email;
  }
  return new SignJWT(claims)
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("60s")
    .sign(new TextEncoder().encode(secret));
}
