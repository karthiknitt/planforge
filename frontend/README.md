# PlanForge Frontend

Next.js 16 App Router application. See [root README](../README.md) for full project setup.

## Dev

```bash
npm install
npm run dev     # http://localhost:3001
```

## Key Commands

```bash
# Lint + format check
npx biome check .

# Format files
npx biome format --write .

# Add a ShadCN component
npx shadcn@latest add <component>

# Push DB schema changes
DATABASE_URL="postgresql://planforge:planforge@localhost:5432/planforge" \
  node_modules/.bin/drizzle-kit push
```

## Environment

Copy `.env.local.example` → `.env.local` and fill in:

```
DATABASE_URL=postgresql://planforge:planforge@localhost:5432/planforge
BETTER_AUTH_SECRET=<random-secret>
NEXT_PUBLIC_BETTER_AUTH_URL=http://localhost:3001
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
NEXT_PUBLIC_RAZORPAY_KEY_ID=
OPENAI_API_KEY=        # for voice transcription (agent feature)
ANTHROPIC_API_KEY=     # for agentic chat
```
