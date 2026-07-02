# Backend Auth Fix — Design

**Status:** Approved, ready for implementation plan.

**Trigger:** Discovered during Cloud Run deployment work
(`docs/plans/2026-07-02-cloud-run-deployment-implementation-plan.md`) — code-quality review
of that plan's deploy workflow flagged that Cloud Run's required `--allow-unauthenticated`
flag would make an existing backend vulnerability internet-reachable for the first time.
Cloud Run Phase 2/3 (the actual GCP/Neon go-live) is paused until this fix lands.

## Problem

Every FastAPI route that needs to know "who is calling" reads a client-supplied `X-User-Id`
header and trusts it verbatim, with zero verification:

```python
def _user_id(x_user_id: str = Header(..., alias="X-User-Id")) -> str:
    return x_user_id
```

Present near-identically in `backend/app/api/routes/{projects,revisions,payments,teams,
rooms,share,export,generate}.py`.

Of the 12 frontend call sites that set this header:
- 3 are server-side (Next.js Route Handlers / Server Components) that legitimately call
  `auth.api.getSession()` first — the *value* they send is trustworthy, but the header
  itself is not verified once it leaves Next.js.
- 8 are Client Components (`layout-viewer.tsx`, `new-project-form.tsx`, `edit-form.tsx`,
  `create-team-form.tsx`, `credit-pack-button.tsx`, `pricing-checkout-button.tsx`,
  `boq-viewer.tsx`) calling the backend directly from the browser using
  `useSession().data.user.id` — trivially spoofable via devtools or curl.
- 1 (`frontend/src/app/api/agent/[projectId]/route.ts`) is nominally server-side but reads
  `userId` straight from the client-supplied JSON body with no session check at all —
  functionally identical risk to the client-side cases.

Net effect: anyone can call the (soon-to-be-public) Cloud Run URL with an arbitrary
`X-User-Id` and read/modify that user's projects, revisions, payments, and team data.

## Architecture

```
Browser --(session cookie, same-origin)--> Next.js catch-all proxy
                                              /api/backend/[...path]/route.ts
    auth.api.getSession() validates the cookie server-side (Better Auth, existing DB)
    mints a 60s HS256 JWT: {user_id, exp} signed with INTERNAL_AUTH_SECRET
    forwards method + body + path to FastAPI with header X-Internal-Auth: <token>
                                              |
                                              v
                                        FastAPI backend (Cloud Run, --allow-unauthenticated)
    get_current_user_id() dependency verifies the JWT signature + expiry
    against the same INTERNAL_AUTH_SECRET -> extracts user_id, or 401
```

Cloud Run stays publicly reachable (required — Vercel has no native Workload Identity
Federation path to GCP IAM without reintroducing a stored service-account key), but every
route now requires a valid short-lived signed token instead of a bare client-asserted id.
The token is minted only after a real session check, server-side, and expires in 60s —
even a leaked/replayed token has a tiny usable window and is scoped to one user.

`health.py:/health` and `share.py:/share/{token}` are unaffected: health checks stay
anonymous by design, and public share links are already correctly authenticated by
possession of the unguessable token itself, not by `X-User-Id`.

**Scope decision:** this fixes the *trust mechanism*, not the *access model*. Every route
that requires a user today keeps requiring one — no new anonymous-generation path (despite
`CLAUDE.md` mentioning "stateless generation, no login required" — the actual
`/projects/{id}/generate` route already requires both `project_id` and a user; reconciling
that stale doc note is out of scope here).

## Backend changes

- New `backend/app/dependencies/auth.py`:
  ```python
  import jwt
  from fastapi import Header, HTTPException, status
  from app.config.settings import settings

  def get_current_user_id(x_internal_auth: str = Header(..., alias="X-Internal-Auth")) -> str:
      try:
          payload = jwt.decode(x_internal_auth, settings.internal_auth_secret, algorithms=["HS256"])
      except jwt.InvalidTokenError:
          raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired internal auth token")
      return payload["user_id"]
  ```
- Add `pyjwt` as a backend dependency (`uv add pyjwt`).
- New required setting `internal_auth_secret: str` in `backend/app/config/settings.py` — no
  default value, so the app fails fast at startup if the secret is unset rather than silently
  trusting nothing (or a guessable default).
- Replace all 7 duplicated `_user_id`/`_get_user_id` functions across
  `projects.py`, `revisions.py`, `payments.py`, `teams.py`, `rooms.py`, `share.py` (only the
  non-public routes), `export.py`, `generate.py` with `Depends(get_current_user_id)`.
  Consolidating 7 copies of the same 2-line function into one shared dependency matches the
  project's existing "extract helpers when used 3+ times" convention.

## Frontend changes

- New `frontend/src/app/api/backend/[...path]/route.ts` exporting `GET`/`POST`/`PUT`/
  `PATCH`/`DELETE` handlers, all delegating to one internal `proxy()` function:
  1. `auth.api.getSession({ headers: await headers() })` — 401 if no session.
  2. Mint a 60s HS256 JWT (`jsonwebtoken` or `jose`) containing `{ user_id: session.user.id }`,
     signed with `INTERNAL_AUTH_SECRET`.
  3. Forward the request to `${BACKEND_URL}/api/${path.join("/")}` with
     `X-Internal-Auth: <token>` in place of the old `X-User-Id` header, preserving method,
     body, and relevant query params.
  4. Stream the backend's response back to the client unchanged.
- All 12 existing call sites switch their fetch target from the Cloud Run URL to
  `/api/backend/<same-path>` (same-origin — no CORS involved for these calls at all).
  `agent/[projectId]/route.ts` stops reading `userId` from the request body; it goes through
  the same proxy path as everything else.
- New env var `INTERNAL_AUTH_SECRET`, set identically on both sides: `backend/.env.example`,
  `frontend/.env.example` (or `.env.local` docs if no example file exists), both
  `docker-compose.yml` services, a new `gh secret set INTERNAL_AUTH_SECRET` entry, one new
  `env_vars` line in the already-written `.github/workflows/deploy-backend.yml`, and a
  matching Vercel project env var (production + preview scopes).

## Testing

- Backend: every test currently setting `X-User-Id` directly needs a token instead. Add a
  `conftest.py` fixture (e.g. `auth_headers(user_id) -> dict`) that mints a valid token using
  a fixed test `internal_auth_secret`, and sweep it across the existing 171 tests
  (mechanical replacement, not new test logic). New tests for `get_current_user_id` itself:
  valid token → correct user_id; expired token → 401; tampered signature → 401; missing
  header → 401 (existing FastAPI `Header(...)` behavior).
- Frontend: new tests for the proxy route's session-check and token-minting (no session →
  401; valid session → token present in outgoing request; token expiry set to 60s).

## Migration

Coordinated breaking change — frontend and backend ship together, no compatibility shim for
the old bare `X-User-Id` header (a shim would just mean the vulnerability survives for
however long the shim lives, defeating the purpose). This lands *before* Cloud Run's first
live deploy (Phase 2/3 of the deployment plan is still paused), so there's no production
traffic to break — the fix arrives before the backend is ever internet-reachable, not as a
post-launch hotfix.

## Out of scope

- A real anonymous/stateless generation endpoint (confirmed with the user — current
  login-gated behavior is intentional to preserve, not a bug).
- Changes to `health.py` or the public share-link model in `share.py`.
- Changes to the Vercel-preview CORS regex already merged on
  `feature/cloud-run-deployment` — that work stands independently; after this fix, most
  browser-facing calls become same-origin (through the new proxy), which shrinks how much
  the CORS regex actually matters, but it should stay for defense-in-depth and because
  Phase 2/3 still needs it for whatever isn't proxied.
