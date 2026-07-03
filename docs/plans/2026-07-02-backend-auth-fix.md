# Backend Auth Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task (per this project's standing convention — do not use executing-plans/parallel session).

**Goal:** Replace the unverified client-supplied `X-User-Id` header (trusted verbatim by every
FastAPI route) with a short-lived signed token minted by a trusted Next.js proxy, closing an
IDOR vulnerability before Cloud Run's first public deploy.

**Architecture:** Every browser call to the backend now goes through one Next.js catch-all
proxy route (`/api/backend/[...path]`) that validates the Better Auth session server-side,
mints a 60-second HS256 JWT containing the verified `user_id`, and forwards the request to
FastAPI with `X-Internal-Auth: <token>` instead of the old raw `X-User-Id` header. FastAPI
verifies the token's signature and expiry via a single shared dependency, replacing 8
duplicated do-nothing "trust the header" functions. Design rationale and full context:
`docs/plans/2026-07-02-backend-auth-fix-design.md` — read that first if anything below seems
under-justified.

**Tech Stack:** FastAPI, PyJWT, pytest; Next.js Route Handlers, `jose` (JWT signing, edge/node
compatible), Better Auth, `bun test`.

---

## Before you start

This is a coordinated breaking change — the old bare `X-User-Id` header stops being trusted
entirely once Task 3 lands, so Tasks 1–8 must all land together before merging (they're safe
to do incrementally on this branch since nothing is deployed publicly yet — Cloud Run Phase
2/3 is paused specifically so this can happen first). Task 9 (env var docs) has one
**[USER RUNS THIS]** sub-step (setting real secret values in GitHub/Vercel) — everything else
is Claude-executable.

---

## Task 1: Backend — add PyJWT dependency and `internal_auth_secret` setting

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/config/settings.py`
- Test: `backend/tests/test_settings_internal_auth.py`

**Step 1: Add the dependency**

```bash
cd backend
uv add pyjwt
```

**Step 2: Write the failing test**

```python
# backend/tests/test_settings_internal_auth.py
import pytest
from pydantic import ValidationError


def test_settings_requires_internal_auth_secret(monkeypatch):
    monkeypatch.delenv("INTERNAL_AUTH_SECRET", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app.config.settings import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_reads_internal_auth_secret_from_env(monkeypatch):
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", "test-secret-value")
    from app.config.settings import Settings

    settings = Settings(_env_file=None)
    assert settings.internal_auth_secret == "test-secret-value"
```

**Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_settings_internal_auth.py -v`
Expected: FAIL — `AttributeError` or the "requires" test fails to raise (field doesn't exist
yet / has a default so it never raises).

**Step 4: Add the field**

In `backend/app/config/settings.py`, add a field with **no default** (so Pydantic requires it
and the app fails fast at startup if unset, instead of silently running with no real auth):

```python
    internal_auth_secret: str
```

Add this field after `database_url` and before `razorpay_key_id`, so the file reads:

```python
from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")

    database_url: str = (
        "postgresql+asyncpg://planforge:planforge@localhost:5432/planforge"
    )
    internal_auth_secret: str
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""


settings = Settings()
```

**Step 5: Set a local dev value so the app still boots**

Add to `backend/.env` (your local, untracked env file — NOT `.env.example` yet, that's Task
9): `INTERNAL_AUTH_SECRET=local-dev-secret-change-me`. If `backend/.env` doesn't exist locally,
create it by copying `.env.example` first.

**Step 6: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_settings_internal_auth.py -v`
Expected: 2 passed

**Step 7: Run full backend suite**

Run: `cd backend && uv run pytest -q`
Expected: every test that boots the app now needs `INTERNAL_AUTH_SECRET` set — if other tests
fail here with a `ValidationError` about a missing field, check `backend/tests/conftest.py`
for how the test app is constructed and set a fixed test value there (e.g.
`monkeypatch.setenv("INTERNAL_AUTH_SECRET", "test-secret")` in a session-scoped autouse
fixture, or pass it via `Settings(internal_auth_secret="test-secret", ...)` if settings are
constructed explicitly for tests). Get this genuinely green before moving on — don't skip
failing tests.

**Step 8: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/config/settings.py backend/tests/test_settings_internal_auth.py
git commit -m "feat(backend): add PyJWT dependency and required internal_auth_secret setting"
```

---

## Task 2: Backend — shared `get_current_user_id` dependency

**Files:**
- Create: `backend/app/dependencies/__init__.py` (empty, if `app/dependencies/` doesn't exist yet)
- Create: `backend/app/dependencies/auth.py`
- Test: `backend/tests/test_dependencies_auth.py`

**Why:** This one function replaces 8 near-identical "trust the header" functions currently
duplicated across `projects.py`, `revisions.py`, `payments.py`, `teams.py`, `rooms.py`,
`share.py`, `export.py`, `generate.py`. It's the single place that decides whether a request
is authenticated.

**Step 1: Write the failing tests**

```python
# backend/tests/test_dependencies_auth.py
import time

import jwt
import pytest
from fastapi import HTTPException

from app.dependencies.auth import get_current_user_id

SECRET = "test-secret-value"


def _token(user_id: str, exp_offset_seconds: int = 60, secret: str = SECRET) -> str:
    payload = {"user_id": user_id, "exp": time.time() + exp_offset_seconds}
    return jwt.encode(payload, secret, algorithm="HS256")


def test_valid_token_returns_user_id(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.auth.settings.internal_auth_secret", SECRET
    )
    token = _token("user-123")
    assert get_current_user_id(x_internal_auth=token) == "user-123"


def test_expired_token_raises_401(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.auth.settings.internal_auth_secret", SECRET
    )
    token = _token("user-123", exp_offset_seconds=-10)
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(x_internal_auth=token)
    assert exc_info.value.status_code == 401


def test_tampered_signature_raises_401(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.auth.settings.internal_auth_secret", SECRET
    )
    token = _token("user-123", secret="wrong-secret")
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(x_internal_auth=token)
    assert exc_info.value.status_code == 401


def test_malformed_token_raises_401(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.auth.settings.internal_auth_secret", SECRET
    )
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(x_internal_auth="not-a-jwt")
    assert exc_info.value.status_code == 401
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_dependencies_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.dependencies'`

**Step 3: Write minimal implementation**

Create `backend/app/dependencies/__init__.py` (empty file) if the directory doesn't exist.

```python
# backend/app/dependencies/auth.py
import jwt
from fastapi import Header, HTTPException, status

from app.config.settings import settings


def get_current_user_id(x_internal_auth: str = Header(..., alias="X-Internal-Auth")) -> str:
    try:
        payload = jwt.decode(
            x_internal_auth, settings.internal_auth_secret, algorithms=["HS256"]
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid or expired internal auth token"
        ) from exc
    return payload["user_id"]
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_dependencies_auth.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add backend/app/dependencies/ backend/tests/test_dependencies_auth.py
git commit -m "feat(backend): add get_current_user_id dependency verifying signed internal tokens"
```

---

## Task 3: Backend — replace all 8 duplicated header-trusting functions

**Files (exact current state, verified on this branch):**

| File | Function name to remove | `Depends(...)` call sites to update |
|---|---|---|
| `backend/app/api/routes/projects.py` | `get_user_id` (line 47-49) | lines 78, 126, 163, 202, 222 |
| `backend/app/api/routes/revisions.py` | `_get_user_id` (line 45-46) | lines 226, 251, 343, 373 |
| `backend/app/api/routes/payments.py` | `_get_user_id` (line 25-26) | lines 54, 92, 124, 170 |
| `backend/app/api/routes/teams.py` | `_get_user_id` (line 16-17) | lines 94, 118, 134, 156, 196, 221 |
| `backend/app/api/routes/rooms.py` | `_user_id` (line 55-56) | lines 251, 276, 295, 328, 363, 398, 461, 485, 518, 602, 719, 761 |
| `backend/app/api/routes/share.py` | `_get_user_id` (line 37-38) | lines 210, 330 only — **do NOT touch** the public `/share/{token}`, `/share/{token}/approve`, `/share/{token}/request-changes` routes, they have no user-id dependency at all and must stay that way |
| `backend/app/api/routes/export.py` | `_user_id` (line 35-36) | lines 89, 134, 178, 560 |
| `backend/app/api/routes/generate.py` | `_user_id` (line 29-30) | line 58 |

Line numbers may have shifted slightly if Tasks 1-2 touched shared files — re-grep each file
for `_user_id\|_get_user_id\|get_user_id` before editing to confirm current line numbers; the
table above is a map of *what* to find, not a guarantee of exact current line numbers.

**Step 1: For each file in the table**

1. Remove the local `_user_id`/`_get_user_id`/`get_user_id` function definition and its
   `Header` import if `Header` is no longer used elsewhere in that file (check before
   removing the import — `rooms.py` still uses `Header` for `X-Project-Id` at its own call
   site, so its `Header` import must stay).
2. Add `from app.dependencies.auth import get_current_user_id` to the file's imports.
3. Replace every `Depends(get_user_id)` / `Depends(_get_user_id)` / `Depends(_user_id)` call
   site with `Depends(get_current_user_id)`.

Do this file by file, running `cd backend && uv run pytest -q` after each file to catch
mistakes early rather than debugging 8 files' worth of changes at once.

**Step 2: Run full backend suite**

Run: `cd backend && uv run pytest -q`
Expected: existing tests that still send a raw `X-User-Id` header will now fail with 401
(the header is no longer read at all) — this is expected and exactly what Task 4 fixes next.
Note which test files fail here; you'll fix them in Task 4.

**Step 3: Commit**

```bash
git add backend/app/api/routes/
git commit -m "refactor(backend): replace 8 duplicated header-trusting functions with get_current_user_id"
```

(It's fine that the suite isn't green yet — Task 4 fixes the tests. Commit anyway so this
refactor is its own reviewable unit; the follow-up test fix is a separate concern.)

---

## Task 4: Backend — fix tests broken by the auth change

**Files:**
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_api_e2e.py`
- Modify: `backend/tests/test_share_token.py`
- Modify: `backend/tests/test_compliance_check_endpoint.py`
- Modify: `backend/tests/test_revision_history.py`

**Why:** Only 4 test files construct `X-User-Id` headers directly (confirmed via
`grep -rl "X-User-Id" backend/tests/`). Rather than making every test mint a real signed JWT
(more moving parts, more test-only crypto code), override `get_current_user_id` in the test
app the same way `get_db` is already overridden in `conftest.py` — this tests business logic
against a controlled identity without re-testing the JWT mechanism itself (that's already
covered by Task 2's dedicated tests).

**Step 1: Add the override to conftest.py**

Read `backend/tests/conftest.py` first (shown in Task 1's exploration — it currently overrides
`get_db` inside the `client` fixture). Add an override for `get_current_user_id` that reads a
plain `X-Test-User-Id` header instead of verifying a real token — this is test-only code, it
never ships:

```python
from app.dependencies.auth import get_current_user_id
from fastapi import Header


def _test_user_id_override(x_test_user_id: str = Header(..., alias="X-Test-User-Id")) -> str:
    return x_test_user_id
```

Add this function near the top of `conftest.py`, and inside the `client` fixture, alongside
the existing `app.dependency_overrides[get_db] = override_get_db` line, add:

```python
    app.dependency_overrides[get_current_user_id] = _test_user_id_override
```

Make sure it's also cleared in the existing `app.dependency_overrides.clear()` teardown line
(it already clears the whole dict, so no extra teardown code needed — just confirm that line
still runs after your edit).

**Step 2: Update the 4 test files**

In each of `test_api_e2e.py`, `test_share_token.py`, `test_compliance_check_endpoint.py`,
`test_revision_history.py`: find every `"X-User-Id"` string and rename it to
`"X-Test-User-Id"`. This is a mechanical rename — the header *value* (the actual user id
string) doesn't change, only the header *name*.

Run: `grep -rln "X-User-Id" backend/tests/` after editing — expected: no output (all
occurrences renamed).

**Step 3: Run full backend suite**

Run: `cd backend && uv run pytest -q`
Expected: all tests pass (same count as before Task 3 broke them — confirm the exact number
by comparing to the last known-good count).

**Step 4: Commit**

```bash
git add backend/tests/
git commit -m "test(backend): override get_current_user_id in test client instead of trusting raw headers"
```

---

## Task 5: Frontend — internal auth token helper

**Files:**
- Create: `frontend/src/lib/internal-auth.ts`
- Test: `frontend/src/lib/internal-auth.test.ts`

**Step 1: Add the `jose` dependency**

```bash
cd frontend
bun add jose
```

**Step 2: Write the failing test**

This will be the first unit test in the frontend codebase — confirm `bun test` picks it up
with no extra config (Bun's test runner auto-discovers `*.test.ts` files, no config needed).

```typescript
// frontend/src/lib/internal-auth.test.ts
import { describe, expect, test } from "bun:test";
import { jwtVerify } from "jose";
import { signInternalAuthToken } from "./internal-auth";

const SECRET = "test-secret-value";

describe("signInternalAuthToken", () => {
  test("produces a token verifiable with the same secret", async () => {
    const token = await signInternalAuthToken("user-123", SECRET);
    const { payload } = await jwtVerify(
      token,
      new TextEncoder().encode(SECRET)
    );
    expect(payload.user_id).toBe("user-123");
  });

  test("token expires in approximately 60 seconds", async () => {
    const token = await signInternalAuthToken("user-123", SECRET);
    const { payload } = await jwtVerify(
      token,
      new TextEncoder().encode(SECRET)
    );
    const now = Math.floor(Date.now() / 1000);
    expect(payload.exp).toBeGreaterThan(now + 50);
    expect(payload.exp).toBeLessThanOrEqual(now + 60);
  });

  test("token signed with a different secret fails verification", async () => {
    const token = await signInternalAuthToken("user-123", SECRET);
    await expect(
      jwtVerify(token, new TextEncoder().encode("wrong-secret"))
    ).rejects.toThrow();
  });
});
```

**Step 3: Run test to verify it fails**

Run: `cd frontend && bun test src/lib/internal-auth.test.ts`
Expected: FAIL — `internal-auth.ts` doesn't exist yet.

**Step 4: Write minimal implementation**

```typescript
// frontend/src/lib/internal-auth.ts
import { SignJWT } from "jose";

export async function signInternalAuthToken(
  userId: string,
  secret: string
): Promise<string> {
  return new SignJWT({ user_id: userId })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("60s")
    .sign(new TextEncoder().encode(secret));
}
```

**Step 5: Run test to verify it passes**

Run: `cd frontend && bun test src/lib/internal-auth.test.ts`
Expected: 3 pass

**Step 6: Commit**

```bash
git add frontend/package.json frontend/bun.lock frontend/src/lib/internal-auth.ts frontend/src/lib/internal-auth.test.ts
git commit -m "feat(frontend): add signInternalAuthToken helper for backend proxy auth"
```

---

## Task 6: Frontend — generic backend proxy route

**Files:**
- Create: `frontend/src/app/api/backend/[...path]/route.ts`

**Step 1: Write the proxy route**

```typescript
// frontend/src/app/api/backend/[...path]/route.ts
import { headers } from "next/headers";
import { type NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { signInternalAuthToken } from "@/lib/internal-auth";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

async function proxy(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
  method: string
): Promise<NextResponse> {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const secret = process.env.INTERNAL_AUTH_SECRET;
  if (!secret) {
    throw new Error("INTERNAL_AUTH_SECRET is not set");
  }
  const token = await signInternalAuthToken(session.user.id, secret);

  const { path } = await params;
  const search = req.nextUrl.search;
  const targetUrl = `${BACKEND_URL}/api/${path.join("/")}${search}`;

  const body =
    method === "GET" || method === "DELETE" ? undefined : await req.text();

  const backendResponse = await fetch(targetUrl, {
    method,
    headers: {
      "Content-Type": req.headers.get("content-type") ?? "application/json",
      "X-Internal-Auth": token,
    },
    body,
  });

  const responseBody = await backendResponse.text();
  return new NextResponse(responseBody, {
    status: backendResponse.status,
    headers: {
      "Content-Type": backendResponse.headers.get("content-type") ?? "application/json",
    },
  });
}

type RouteContext = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: RouteContext) {
  return proxy(req, ctx, "GET");
}
export async function POST(req: NextRequest, ctx: RouteContext) {
  return proxy(req, ctx, "POST");
}
export async function PUT(req: NextRequest, ctx: RouteContext) {
  return proxy(req, ctx, "PUT");
}
export async function PATCH(req: NextRequest, ctx: RouteContext) {
  return proxy(req, ctx, "PATCH");
}
export async function DELETE(req: NextRequest, ctx: RouteContext) {
  return proxy(req, ctx, "DELETE");
}
```

**Step 2: Type-check and lint**

Run: `cd frontend && bunx tsc --noEmit && bunx biome check src/app/api/backend/`
Expected: no errors. Fix any type issues before proceeding (e.g. if this Next.js version's
Route Handler context type differs, match whatever convention `frontend/src/app/api/team/members/route.ts` already uses for its `{ params }` type — read that file for the exact
pattern this project uses).

**Step 3: Commit**

```bash
git add frontend/src/app/api/backend/
git commit -m "feat(frontend): add generic authenticated proxy route to backend"
```

---

## Task 7: Frontend — migrate all call sites to the proxy

**Files (all 12 call sites currently sending `X-User-Id` directly to the backend):**

| File | Line(s) | Current pattern | New pattern |
|---|---|---|---|
| `frontend/src/app/api/team/members/route.ts` | 21 | `${backendUrl}/api/...` + `X-User-Id` header | `/api/backend/...`, drop the `X-User-Id` header entirely |
| `frontend/src/app/api/team/invite/route.ts` | 24 | same | same |
| `frontend/src/app/(app)/projects/[id]/page.tsx` | 38 | same | same |
| `frontend/src/app/api/agent/[projectId]/route.ts` | 313 (reads `userId` from body at 234-238) | trusts client body `userId`, no session check | remove body-`userId` trust entirely; call `/api/backend/...` (the proxy re-validates session itself) |
| `frontend/src/app/(app)/projects/[id]/layout-viewer.tsx` | 386, 412, 427, 526, 567, 595, 661, 689, 712, 739, 755, 792, 827 | `${NEXT_PUBLIC_API_URL}/api/...` + `X-User-Id` from `useSession()` | `/api/backend/...`, drop the `X-User-Id` header |
| `frontend/src/app/(app)/projects/new/new-project-form.tsx` | 448 | same | same |
| `frontend/src/app/(app)/projects/[id]/edit/edit-form.tsx` | 250 | same | same |
| `frontend/src/app/(app)/team/create-team-form.tsx` | 33 | same | same |
| `frontend/src/components/credit-pack-button.tsx` | 37, 73 | same | same |
| `frontend/src/components/pricing-checkout-button.tsx` | 35, 65 | same | same |
| `frontend/src/components/boq-viewer.tsx` | 55, 81 | same | same |

**Do NOT touch** these — they call genuinely public/unauthenticated backend routes and never
sent `X-User-Id` in the first place: `frontend/src/app/share/[token]/page.tsx`,
`frontend/src/app/(marketing)/gallery/page.tsx`, `frontend/src/components/approval-actions.tsx`.

**Step 1: For each file in the table**

1. Change the fetch target from whatever backend-URL env var it was using
   (`NEXT_PUBLIC_API_URL`, `BACKEND_URL`, or `NEXT_PUBLIC_BACKEND_URL` — three different names
   were used inconsistently pre-fix) to a relative path: `/api/backend/<same path segment>`.
   Since these calls now go same-origin through the proxy, no backend-URL env var is needed
   at these call sites at all.
2. Remove the `X-User-Id` header from the request (the proxy adds `X-Internal-Auth` itself,
   server-side — the client never needs to know about it).
3. For `layout-viewer.tsx`, `new-project-form.tsx`, `edit-form.tsx`, `create-team-form.tsx`,
   `credit-pack-button.tsx`, `pricing-checkout-button.tsx`, `boq-viewer.tsx`: if `useSession()`
   was only being called to extract `user.id` for the header (and not used for anything else
   in that component, e.g. showing the user's name), the `useSession()` call and its import
   can be removed too — check each file for other uses of `session` before removing.
4. For `frontend/src/app/api/agent/[projectId]/route.ts`: remove the `userId` destructuring
   from the request body (lines 234-238) and the manual `if (!userId) return 401` check — the
   proxy pattern means this route itself should now also call the backend via
   `/api/backend/...` rather than constructing backend URLs directly, OR (simpler, since this
   file is itself a Next.js server route, not a browser call site) it can call
   `auth.api.getSession()` directly and mint its own token the same way the proxy does, since
   it's not merely forwarding an arbitrary path — read the full file first to decide which
   fits its existing structure better, and prefer minimal disruption to its non-auth logic.

**Step 2: Verify no remaining direct backend calls with the old pattern**

Run: `grep -rln "X-User-Id" frontend/src/` — expected: no output.
Run: `grep -rln "NEXT_PUBLIC_API_URL\|BACKEND_URL\|NEXT_PUBLIC_BACKEND_URL" frontend/src/` —
expected: only `share/[token]/page.tsx`, `gallery/page.tsx`, `approval-actions.tsx` remain
(the genuinely-public call sites left untouched per this task's scope).

**Step 3: Type-check and lint**

Run: `cd frontend && bunx tsc --noEmit && bunx biome check src/`
Expected: no errors.

**Step 4: Manual smoke test**

Start the stack (`docker-compose up` or `dev` per this project's PM2 convention — see
`backend/.env` has `INTERNAL_AUTH_SECRET` set from Task 1, and set the same value in
`frontend/.env.local` as `INTERNAL_AUTH_SECRET=local-dev-secret-change-me`), log in, and
exercise: create a project, generate layouts, edit a room, view BOQ. Confirm nothing 401s
that shouldn't, and confirm opening browser devtools network tab shows calls going to
`/api/backend/...` (same-origin), not directly to the Cloud Run/local backend URL.

**Step 5: Commit**

```bash
git add frontend/src/
git commit -m "refactor(frontend): route all authenticated backend calls through the proxy"
```

---

## Task 8: Document `INTERNAL_AUTH_SECRET` everywhere it's needed

**Files:**
- Modify: `backend/.env.example`
- Modify: `frontend/.env.example` (create if it doesn't exist — check first)
- Modify: `docker-compose.yml`

**Step 1: Backend `.env.example`**

Add: `INTERNAL_AUTH_SECRET=changeme-generate-a-real-random-secret`

**Step 2: Frontend `.env.example`**

Check `ls frontend/.env.example` first. Add or create with (at minimum):
```
INTERNAL_AUTH_SECRET=changeme-generate-a-real-random-secret
BACKEND_URL=http://localhost:8000
```
If the file already has other vars (check for existing `BETTER_AUTH_SECRET`,
`NEXT_PUBLIC_BETTER_AUTH_URL`, `DATABASE_URL`, etc. from the real `.env.local` structure),
append rather than overwrite.

**Step 3: `docker-compose.yml`**

Add `INTERNAL_AUTH_SECRET: local-dev-secret-change-me` to both the `backend` and `frontend`
services' `environment:` blocks (same value on both, since they must share the secret to
verify each other's tokens).

**Step 4: Commit**

```bash
git add backend/.env.example frontend/.env.example docker-compose.yml
git commit -m "docs: document INTERNAL_AUTH_SECRET across backend, frontend, and docker-compose"
```

**Step 5: [USER RUNS THIS] — set real secret values**

This step needs real secret material and account access Claude doesn't have:

```bash
# Generate a real random secret (do this once, use the same value everywhere below)
openssl rand -base64 32

# GitHub Actions secret (for the already-written .github/workflows/deploy-backend.yml —
# also add one new line to that workflow's env_vars block: INTERNAL_AUTH_SECRET=${{ secrets.INTERNAL_AUTH_SECRET }})
gh secret set INTERNAL_AUTH_SECRET --body "<the generated secret>"

# Vercel — production and preview scopes, same value
vercel env add INTERNAL_AUTH_SECRET production
vercel env add INTERNAL_AUTH_SECRET preview
```

---

## Task 9: Full verification

**Step 1: Backend**

Run: `cd backend && uv run ruff format --check . && uv run ruff check . && uv run pytest -q`
Expected: all green, same or greater test count than before this plan started.

**Step 2: Frontend**

Run: `cd frontend && bunx biome check . && bunx tsc --noEmit && bun test`
Expected: all green.

**Step 3: Confirm no dangling references**

Run: `grep -rn "X-User-Id" backend/ frontend/src/ --include="*.py" --include="*.ts" --include="*.tsx"`
Expected: no output at all (fully removed, including from tests — Task 4 renamed those to
`X-Test-User-Id`).

**Step 4: Report**

Summarize: final backend test count, final frontend test count, confirmation that the manual
smoke test (Task 7 Step 4) passed, and that this branch (`fix/backend-auth-verification`) is
ready for a PR into `main` — do not merge directly, open a PR per this project's standing
git convention.
