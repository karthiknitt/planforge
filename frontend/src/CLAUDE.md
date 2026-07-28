# frontend/src — conventions

Next.js App Router app. `app/` routes, `components/` (ShadCN in `components/ui/`,
motion in `components/motion/`), `db/` Drizzle schema for Better Auth, `hooks/`,
`lib/` (agent/backend glue, pure helpers), `test/` shared test setup.

## Rules

- **Server Components by default** — Client Components only for interactivity/state.
- **Never write raw HTML UI elements when a ShadCN component exists** — check
  `components/ui/` first.
- **Biome only** — `bun run lint` / `bun run format`, no ESLint/Prettier config to add.
- **Tests are colocated** as `*.test.ts` next to the source file (see `lib/`,
  `components/*.test.ts`), run with `bun test` (Bun's runner, not Vitest). E2E is
  Playwright via `bun run test:e2e`.
- **Auth tables only** go through Drizzle (`db/`) — everything else is backend-owned
  Postgres via SQLAlchemy, reached through `/api/` routes or `backend-fetch.ts`.

## Gotchas

- **AI SDK v6 tool parts, not v4.** A tool result is `part.type === "tool-<name>"` or
  `"dynamic-tool"` with `part.state === "output-available"` — not v4's
  `"tool-invocation"`/`"result"`. Use `chat-parts.ts` (`isToolUIPart`/`getToolName`)
  rather than checking `part.type` by hand; a stale v4 check silently breaks tool
  rendering (see root `CLAUDE.md` issue 12).
- **Cloud Run cold starts run ~20–25s.** `backend-fetch.ts` takes a per-call
  `timeoutMs` for this reason — the default is too short for agent tool calls, which
  pass 45s. Don't hardcode a short abort on a new backend call.
- **Provider fallback chain** (`agent-model-chain.ts` + `agent-errors.ts`) advances on
  401/402/404/429/5xx/network errors, not just billing errors — if you add a new
  provider, make sure its error shape maps into `shouldFallback`.
