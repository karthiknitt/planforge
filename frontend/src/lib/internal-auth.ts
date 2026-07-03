import { SignJWT } from "jose";

export async function signInternalAuthToken(userId: string, secret: string): Promise<string> {
  if (!secret) {
    throw new Error("signInternalAuthToken: secret must not be empty");
  }
  return new SignJWT({ user_id: userId })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("60s")
    .sign(new TextEncoder().encode(secret));
}
