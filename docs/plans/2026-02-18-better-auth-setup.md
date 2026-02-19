# Better Auth Setup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Configure Better Auth with Drizzle adapter and email/password auth, wire up the Next.js API route handler, generate and apply the auth DB schema, and create the auth client — giving PlanForge working user registration and login.

**Architecture:** Better Auth server config lives at `src/lib/auth.ts`. It uses the Drizzle adapter pointed at the same `db` instance in `src/db/index.ts`. The Next.js catch-all API route at `app/api/auth/[...all]/route.ts` handles all auth HTTP traffic. The React auth client at `src/lib/auth-client.ts` provides hooks for sign-in/sign-up/session in Client Components.

**Tech Stack:** Better Auth 1.4+, Drizzle ORM, PostgreSQL (via `postgres` npm package), Next.js 16 App Router, TypeScript

---

## Pre-flight: Start Database

Before running any tasks, start the PostgreSQL container:

```bash
cd D:/PlanForge
docker compose up db -d
```

Wait for it to be healthy:
```bash
docker compose ps
```

Expected: `db` shows `(healthy)`.

---

## Task 1: Fix npm lockfile sync

**Files:**
- No new files — just ensures node_modules is consistent with package.json

**Step 1: Run npm install to resync lockfile**

```bash
cd D:/PlanForge/frontend
npm install
```

This ensures `better-auth`, `drizzle-orm`, `postgres` and all other deps are fully linked. The previous `ECONNRESET` may have left the lockfile stale.

**Step 2: Verify better-auth is accessible**

```bash
cd D:/PlanForge/frontend
node -e "require('better-auth'); console.log('ok')"
```

Expected: `ok`

**Step 3: No commit needed** — package-lock.json changes are auto-committed with install.

If the install itself fails due to network, retry once. If it continues to fail, check internet connectivity before proceeding.

---

## Task 2: Create Auth Server Config

**Files:**
- Create: `frontend/src/lib/auth.ts`

**Step 1: Create `src/lib/` directory**

```bash
mkdir -p D:/PlanForge/frontend/src/lib
```

**Step 2: Create `frontend/src/lib/auth.ts`**

```typescript
import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { nextCookies } from "better-auth/integrations/next-js";
import { db } from "@/db";
import * as schema from "@/db/schema";

export const auth = betterAuth({
  database: drizzleAdapter(db, {
    provider: "pg",
    schema,
  }),
  emailAndPassword: {
    enabled: true,
  },
  session: {
    cookieCache: {
      enabled: true,
      maxAge: 60 * 5, // 5 minutes
    },
  },
  plugins: [nextCookies()],
});

export type Session = typeof auth.$Infer.Session;
export type User = typeof auth.$Infer.Session.user;
```

**Step 3: Run Biome check**

```bash
cd D:/PlanForge/frontend
npx biome check src/lib/auth.ts
```

Fix any lint errors before proceeding.

**Step 4: No commit yet** — commit after schema is generated and applied.

---

## Task 3: Generate Better Auth Drizzle Schema

**Files:**
- Modify: `frontend/src/db/schema.ts`

Better Auth CLI reads `src/lib/auth.ts` and outputs the Drizzle schema for all tables it needs (user, session, account, verification).

**Step 1: Run the Better Auth CLI generate command**

```bash
cd D:/PlanForge/frontend
npx @better-auth/cli@latest generate --output src/db/schema.ts
```

If it asks for confirmation, answer yes.

This will REPLACE the placeholder content in `src/db/schema.ts` with the full Drizzle schema for auth tables.

**Step 2: Verify schema.ts was populated**

Read `frontend/src/db/schema.ts` and confirm it contains table definitions for:
- `user` table (id, name, email, emailVerified, image, createdAt, updatedAt)
- `session` table (id, expiresAt, token, createdAt, updatedAt, ipAddress, userAgent, userId)
- `account` table
- `verification` table

**Step 3: Run Biome check on schema**

```bash
cd D:/PlanForge/frontend
npx biome check src/db/schema.ts
```

Auto-fix if needed:
```bash
npx biome check --write src/db/schema.ts
```

**Step 4: No commit yet** — commit after schema is applied to DB.

---

## Task 4: Apply Schema to PostgreSQL (drizzle-kit push)

**Files:**
- No new files — applies schema.ts to the running PostgreSQL instance

**Pre-condition:** PostgreSQL container must be running (`docker compose up db -d`).

**Step 1: Run drizzle-kit push**

```bash
cd D:/PlanForge/frontend
npx drizzle-kit push
```

This reads `drizzle.config.ts` → connects to `DATABASE_URL` from `.env.local` → creates the auth tables in PostgreSQL.

Expected output: Something like:
```
[✓] Changes applied
```

If it asks to confirm destructive operations, type `yes` — this is a fresh DB.

**Step 2: Verify tables were created**

```bash
cd D:/PlanForge
docker compose exec db psql -U planforge -d planforge -c "\dt"
```

Expected: Output lists `user`, `session`, `account`, `verification` tables.

**Step 3: Commit all auth schema work**

```bash
cd D:/PlanForge
git add frontend/src/lib/auth.ts frontend/src/db/schema.ts
git commit -m "feat: add Better Auth server config with Drizzle adapter and email/password"
```

---

## Task 5: Create Next.js API Route Handler

**Files:**
- Create: `frontend/src/app/api/auth/[...all]/route.ts`

**Step 1: Create the directory**

```bash
mkdir -p "D:/PlanForge/frontend/src/app/api/auth/[...all]"
```

**Step 2: Create `route.ts`**

```typescript
import { auth } from "@/lib/auth";
import { toNextJsHandler } from "better-auth/next-js";

export const { GET, POST } = toNextJsHandler(auth);
```

**Step 3: Run Biome check**

```bash
cd D:/PlanForge/frontend
npx biome check "src/app/api/auth/[...all]/route.ts"
```

**Step 4: Verify build still passes**

```bash
cd D:/PlanForge/frontend
npm run build 2>&1 | tail -10
```

Expected: Build succeeds.

**Step 5: Commit**

```bash
cd D:/PlanForge
git add "frontend/src/app/api/auth/[...all]/route.ts"
git commit -m "feat: mount Better Auth handler at /api/auth/[...all]"
```

---

## Task 6: Create Auth Client

**Files:**
- Create: `frontend/src/lib/auth-client.ts`

**Step 1: Create `frontend/src/lib/auth-client.ts`**

```typescript
import { createAuthClient } from "better-auth/react";

export const authClient = createAuthClient({
  baseURL: process.env.NEXT_PUBLIC_BETTER_AUTH_URL ?? "http://localhost:3000",
});

export const { signIn, signUp, signOut, useSession } = authClient;
```

**Step 2: Add `NEXT_PUBLIC_BETTER_AUTH_URL` to env files**

Append to `frontend/.env.local`:
```
NEXT_PUBLIC_BETTER_AUTH_URL=http://localhost:3000
```

Append to `frontend/.env.local.example`:
```
NEXT_PUBLIC_BETTER_AUTH_URL=http://localhost:3000
```

**Step 3: Run Biome check**

```bash
cd D:/PlanForge/frontend
npx biome check src/lib/auth-client.ts
```

**Step 4: Verify build**

```bash
cd D:/PlanForge/frontend
npm run build 2>&1 | tail -10
```

Expected: Build succeeds.

**Step 5: Commit**

```bash
cd D:/PlanForge
git add frontend/src/lib/auth-client.ts frontend/.env.local.example
git commit -m "feat: add Better Auth React client with signIn, signUp, signOut, useSession"
```

---

## Task 7: Smoke Test — Registration via API

**Goal:** Verify the full auth stack works end-to-end by calling the sign-up endpoint directly.

**Step 1: Start the dev server in background**

```bash
cd D:/PlanForge/frontend
npm run dev &
sleep 5
```

**Step 2: Register a test user via curl**

```bash
curl -s -X POST http://localhost:3000/api/auth/sign-up/email \
  -H "Content-Type: application/json" \
  -d '{"email":"test@planforge.local","password":"TestPass123!","name":"Test User"}' \
  | head -c 200
```

Expected: JSON response with `token`, `user.id`, `user.email` — no error.

**Step 3: Sign in with the test user**

```bash
curl -s -X POST http://localhost:3000/api/auth/sign-in/email \
  -H "Content-Type: application/json" \
  -d '{"email":"test@planforge.local","password":"TestPass123!"}' \
  | head -c 200
```

Expected: JSON with session token.

**Step 4: Check session in database**

```bash
cd D:/PlanForge
docker compose exec db psql -U planforge -d planforge \
  -c "SELECT email, name FROM \"user\" LIMIT 5;"
```

Expected: Shows `test@planforge.local` row.

**Step 5: Kill dev server**

```bash
kill %1 2>/dev/null || true
```

**Step 6: Final commit**

```bash
cd D:/PlanForge
git add .
git commit -m "chore: Better Auth smoke test passed — auth stack verified end-to-end"
```

---

## Done: Better Auth Complete

At this point you have:
- `src/lib/auth.ts` — server auth config (Drizzle adapter, email/password, nextCookies)
- `src/db/schema.ts` — Drizzle schema with auth tables applied to PostgreSQL
- `src/app/api/auth/[...all]/route.ts` — Next.js handler for all auth endpoints
- `src/lib/auth-client.ts` — React client with `signIn`, `signUp`, `signOut`, `useSession`
- Working registration and login via the API

**Next step:** Build the login/sign-up UI pages using the `frontend-design` skill + ShadCN components.
