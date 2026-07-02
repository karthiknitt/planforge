import { SignJWT } from "jose";

export async function signInternalAuthToken(userId: string, secret: string): Promise<string> {
  return new SignJWT({ user_id: userId })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("60s")
    .sign(new TextEncoder().encode(secret));
}
