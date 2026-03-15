# PlanForge Frontend

Next.js 16 App Router application. See [root README](../README.md) for full project setup.

## Dev

```bash
bun install
bun dev     # http://localhost:3001
```

## Key Commands

```bash
# Lint + format check
bun run lint

# Format files
bun run format

# Unit tests (Bun test runner)
bun test

# Add a ShadCN component
bunx shadcn@latest add <component>

# Push DB schema changes
DATABASE_URL="postgresql://planforge:planforge@localhost:5432/planforge" \
  bunx drizzle-kit push
```

## Environment

Copy `.env.local.example` → `.env.local` and fill in:

```
DATABASE_URL=postgresql://planforge:planforge@localhost:5432/planforge
BETTER_AUTH_SECRET=<random-secret>
NEXT_PUBLIC_BETTER_AUTH_URL=http://localhost:3001
NEXT_PUBLIC_API_URL=http://localhost:8002
NEXT_PUBLIC_RAZORPAY_KEY_ID=rzp_test_...
OPENAI_API_KEY=sk-...        # voice transcription (agent feature)
ANTHROPIC_API_KEY=sk-ant-... # agentic chat
```
