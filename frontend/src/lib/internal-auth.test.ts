/// <reference types="bun" />
import { describe, expect, test } from "bun:test";
import { jwtVerify } from "jose";
import { signInternalAuthToken } from "./internal-auth";

const SECRET = "test-secret-value";

describe("signInternalAuthToken", () => {
  test("produces a token verifiable with the same secret", async () => {
    const token = await signInternalAuthToken("user-123", SECRET);
    const { payload } = await jwtVerify(token, new TextEncoder().encode(SECRET));
    expect(payload.user_id).toBe("user-123");
  });

  test("token expires in approximately 60 seconds", async () => {
    const token = await signInternalAuthToken("user-123", SECRET);
    const { payload } = await jwtVerify(token, new TextEncoder().encode(SECRET));
    const now = Math.floor(Date.now() / 1000);
    expect(payload.exp).toBeGreaterThan(now + 50);
    expect(payload.exp).toBeLessThanOrEqual(now + 60);
  });

  test("token signed with a different secret fails verification", async () => {
    const token = await signInternalAuthToken("user-123", SECRET);
    await expect(jwtVerify(token, new TextEncoder().encode("wrong-secret"))).rejects.toThrow();
  });

  test("throws when secret is empty", async () => {
    await expect(signInternalAuthToken("user-123", "")).rejects.toThrow("secret must not be empty");
  });

  test("includes an email claim when an email is provided", async () => {
    const token = await signInternalAuthToken("user-123", SECRET, "person@example.com");
    const { payload } = await jwtVerify(token, new TextEncoder().encode(SECRET));
    expect(payload.email).toBe("person@example.com");
  });

  test("omits the email claim when no email is provided", async () => {
    const token = await signInternalAuthToken("user-123", SECRET);
    const { payload } = await jwtVerify(token, new TextEncoder().encode(SECRET));
    expect(payload.email).toBeUndefined();
  });
});
