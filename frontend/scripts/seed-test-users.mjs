/**
 * Seed script — creates 3 test users with known credentials for feature gating QA.
 *
 * Usage (from project root):
 *   cd frontend && npm run seed
 *
 * Or directly:
 *   cd frontend && node scripts/seed-test-users.mjs
 *
 * Requires PostgreSQL to be running (docker compose up db -d).
 * The script is idempotent — safe to run multiple times.
 *
 * Password hash format replicates oslo/password Scrypt (used by Better Auth):
 *   <base64(scrypt(password, salt, 64, N=16384 r=8 p=1))>:<salt>
 */

import { scrypt, randomBytes } from "node:crypto";
import { promisify } from "node:util";
import postgres from "postgres";

const scryptAsync = promisify(scrypt);

// Matches oslo alphabet("a-z", "A-Z", "0-9")
const ALPHABET =
  "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

/** Unbiased random string — same algorithm as oslo generateRandomString */
function generateId(length = 21) {
  const result = [];
  // 62 chars: threshold = floor(256/62)*62 = 248 (rejection sampling, no bias)
  while (result.length < length) {
    const bytes = randomBytes(length * 3);
    for (const byte of bytes) {
      if (result.length >= length) break;
      if (byte < 248) result.push(ALPHABET[byte % 62]);
    }
  }
  return result.join("");
}

/**
 * Replicates oslo/password Scrypt.hash()
 * Format: base64(64-byte-key) + ":" + salt
 */
async function hashPassword(password) {
  const salt = generateId(16);
  const key = await scryptAsync(password, salt, 64, { N: 16384, r: 8, p: 1 });
  return `${Buffer.from(key).toString("base64")}:${salt}`;
}

// ── Test users ────────────────────────────────────────────────────────────────

const TEST_USERS = [
  {
    name: "Free Tester",
    email: "free@planforge.dev",
    password: "Test@1234",
    planTier: "free",
    planExpiresAt: null,
  },
  {
    name: "Basic Tester",
    email: "basic@planforge.dev",
    password: "Test@1234",
    planTier: "basic",
    planExpiresAt: new Date("2099-12-31T23:59:59Z"),
  },
  {
    name: "Pro Tester",
    email: "pro@planforge.dev",
    password: "Test@1234",
    planTier: "pro",
    planExpiresAt: new Date("2099-12-31T23:59:59Z"),
  },
];

// ── Main ──────────────────────────────────────────────────────────────────────

const DATABASE_URL =
  process.env.DATABASE_URL ??
  "postgresql://planforge:planforge@localhost:5432/planforge";

async function seed() {
  console.log("PlanForge — Seeding test users");
  console.log(`DB: ${DATABASE_URL.replace(/:\/\/.*@/, "://<creds>@")}\n`);

  const sql = postgres(DATABASE_URL);
  const now = new Date();

  for (const u of TEST_USERS) {
    const existing =
      await sql`SELECT id FROM "user" WHERE email = ${u.email}`;

    if (existing.length > 0) {
      // User already exists — ensure plan_tier is correct
      await sql`
        UPDATE "user"
        SET plan_tier = ${u.planTier},
            plan_expires_at = ${u.planExpiresAt},
            updated_at = ${now}
        WHERE email = ${u.email}
      `;
      console.log(`  ↻  ${u.email}  (${u.planTier}) — already exists, plan updated`);
      continue;
    }

    const userId = generateId(21);
    const accountId = generateId(21);
    const hashedPassword = await hashPassword(u.password);

    // Insert into Better Auth "user" table (Drizzle-managed)
    await sql`
      INSERT INTO "user" (
        id, name, email, email_verified,
        plan_tier, plan_expires_at,
        created_at, updated_at
      ) VALUES (
        ${userId}, ${u.name}, ${u.email}, ${true},
        ${u.planTier}, ${u.planExpiresAt},
        ${now}, ${now}
      )
    `;

    // Insert credential account (provider_id = 'credential', account_id = user id)
    await sql`
      INSERT INTO account (
        id, account_id, provider_id, user_id,
        password, created_at, updated_at
      ) VALUES (
        ${accountId}, ${userId}, 'credential', ${userId},
        ${hashedPassword}, ${now}, ${now}
      )
    `;

    console.log(`  ✓  ${u.email}  (${u.planTier}) — created`);
  }

  await sql.end();

  console.log("\n─────────────────────────────────────────────");
  console.log("Test credentials (all passwords: Test@1234)");
  console.log("─────────────────────────────────────────────");
  for (const u of TEST_USERS) {
    console.log(`  ${u.planTier.padEnd(5)}  ${u.email}`);
  }
  console.log("─────────────────────────────────────────────\n");
}

seed().catch((err) => {
  console.error("Seed failed:", err.message);
  process.exit(1);
});
