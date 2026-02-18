# Monorepo Scaffold Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Scaffold the complete PlanForge monorepo with a working FastAPI backend, Next.js frontend, PostgreSQL database, and Docker Compose — ready for feature development.

**Architecture:** Monorepo with `/frontend` (Next.js App Router + Better Auth + Tailwind) and `/backend` (FastAPI + uv + Shapely + ReportLab). Docker Compose orchestrates all three services (frontend, backend, postgres) for local dev. Auth is Better Auth on the Next.js side talking directly to PostgreSQL.

**Tech Stack:** Next.js 15, TypeScript, Tailwind CSS v4, Better Auth, FastAPI, Python 3.12, uv, Shapely, ReportLab, PostgreSQL 16, Docker Compose

---

## Task 1: Git Repository Initialization

**Files:**
- Create: `D:/PlanForge/.gitignore`

**Step 1: Initialize git repo**

```bash
cd D:/PlanForge
git init
```

Expected: `Initialized empty Git repository in D:/PlanForge/.git/`

**Step 2: Create root `.gitignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
.venv/
.uv/
dist/
*.egg-info/
.pytest_cache/
.ruff_cache/
htmlcov/
.coverage

# Node
node_modules/
.next/
.turbo/
out/

# Env files
.env
.env.local
.env.*.local

# OS
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
*.swp

# Docker volumes
postgres_data/
```

**Step 3: Commit**

```bash
cd D:/PlanForge
git add .gitignore
git commit -m "chore: init repo with gitignore"
```

---

## Task 2: Backend Directory Structure

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.python-version`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/routes/__init__.py`
- Create: `backend/app/api/routes/health.py`
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/config/__init__.py`
- Create: `backend/app/config/compliance_rules.json`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_health.py`

**Step 1: Create backend directory tree**

```bash
mkdir -p D:/PlanForge/backend/app/api/routes
mkdir -p D:/PlanForge/backend/app/core
mkdir -p D:/PlanForge/backend/app/models
mkdir -p D:/PlanForge/backend/app/config
mkdir -p D:/PlanForge/backend/tests
touch D:/PlanForge/backend/app/__init__.py
touch D:/PlanForge/backend/app/api/__init__.py
touch D:/PlanForge/backend/app/api/routes/__init__.py
touch D:/PlanForge/backend/app/core/__init__.py
touch D:/PlanForge/backend/app/models/__init__.py
touch D:/PlanForge/backend/app/config/__init__.py
touch D:/PlanForge/backend/tests/__init__.py
```

**Step 2: Set Python version**

Create `backend/.python-version`:
```
3.12
```

**Step 3: Initialize uv project**

```bash
cd D:/PlanForge/backend
uv init --no-readme
uv python pin 3.12
```

**Step 4: Add backend dependencies**

```bash
cd D:/PlanForge/backend
uv add fastapi uvicorn[standard] shapely reportlab sqlalchemy asyncpg pydantic-settings python-dotenv
uv add --dev pytest pytest-asyncio httpx
```

**Step 5: Create `backend/pyproject.toml` additions**

After `uv init`, ensure `[tool.pytest.ini_options]` is present:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Step 6: Create `backend/app/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import health

app = FastAPI(title="PlanForge API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
```

**Step 7: Create `backend/app/api/routes/health.py`**

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
def health_check():
    return {"status": "ok", "service": "planforge-api"}
```

**Step 8: Create `backend/app/config/compliance_rules.json`**

```json
{
  "min_bedroom_sqm": 9.5,
  "min_kitchen_sqm": 7.0,
  "min_toilet_sqm": 3.0,
  "min_stair_width_mm": 900,
  "external_wall_thickness_mm": 230,
  "internal_wall_thickness_mm": 115,
  "max_beam_span_m": 4.5,
  "max_floor_coverage_pct": 70
}
```

**Step 9: Write the health test**

Create `backend/tests/test_health.py`:
```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_returns_ok():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

**Step 10: Run tests**

```bash
cd D:/PlanForge/backend
uv run pytest tests/test_health.py -v
```

Expected: `PASSED tests/test_health.py::test_health_returns_ok`

**Step 11: Verify dev server starts**

```bash
cd D:/PlanForge/backend
uv run uvicorn app.main:app --reload --port 8000
```

Visit: `http://localhost:8000/api/health` → `{"status":"ok","service":"planforge-api"}`
Visit: `http://localhost:8000/docs` → Swagger UI

Kill with Ctrl+C.

**Step 12: Commit**

```bash
cd D:/PlanForge
git add backend/
git commit -m "feat: scaffold FastAPI backend with health check and compliance config"
```

---

## Task 3: Frontend Directory Structure (Next.js)

**Files:**
- Create: `frontend/` — via `create-next-app`

**Step 1: Scaffold Next.js app**

```bash
cd D:/PlanForge
npx create-next-app@latest frontend \
  --typescript \
  --tailwind \
  --eslint \
  --app \
  --src-dir \
  --import-alias "@/*" \
  --no-turbopack
```

When prompted, accept defaults. This creates `frontend/` with:
- `src/app/` (App Router)
- `tailwind.config.ts`
- `tsconfig.json`
- `package.json`

**Step 2: Install additional frontend deps**

```bash
cd D:/PlanForge/frontend
npm install better-auth
```

**Step 3: Clean up default Next.js boilerplate**

Replace `frontend/src/app/page.tsx` with a minimal placeholder:
```tsx
export default function Home() {
  return (
    <main className="flex min-h-screen items-center justify-center">
      <h1 className="text-2xl font-bold">PlanForge</h1>
    </main>
  );
}
```

Replace `frontend/src/app/globals.css` — keep only Tailwind directives:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

**Step 4: Add `.env.local` template**

Create `frontend/.env.local.example`:
```env
BETTER_AUTH_SECRET=change-me-in-production
BETTER_AUTH_URL=http://localhost:3000
DATABASE_URL=postgresql://planforge:planforge@localhost:5432/planforge
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Step 5: Copy to actual env file**

```bash
cp D:/PlanForge/frontend/.env.local.example D:/PlanForge/frontend/.env.local
```

**Step 6: Verify dev server starts**

```bash
cd D:/PlanForge/frontend
npm run dev
```

Visit `http://localhost:3000` — should show "PlanForge" heading. Kill with Ctrl+C.

**Step 7: Commit**

```bash
cd D:/PlanForge
git add frontend/
git commit -m "feat: scaffold Next.js frontend with Tailwind and Better Auth"
```

---

## Task 4: Docker Compose for Local Development

**Files:**
- Create: `docker-compose.yml`
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `backend/.env.example`

**Step 1: Create `backend/.env.example`**

```env
DATABASE_URL=postgresql+asyncpg://planforge:planforge@db:5432/planforge
```

**Step 2: Create `backend/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

COPY app/ ./app/

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 3: Create `frontend/Dockerfile`**

```dockerfile
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
```

**Step 4: Create root `docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: planforge
      POSTGRES_PASSWORD: planforge
      POSTGRES_DB: planforge
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U planforge"]
      interval: 5s
      timeout: 5s
      retries: 5

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://planforge:planforge@db:5432/planforge
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./backend/app:/app/app

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      BETTER_AUTH_SECRET: dev-secret-change-in-prod
      BETTER_AUTH_URL: http://localhost:3000
      DATABASE_URL: postgresql://planforge:planforge@db:5432/planforge
      NEXT_PUBLIC_API_URL: http://localhost:8000
    depends_on:
      - backend

volumes:
  postgres_data:
```

**Step 5: Start only the database (most useful for local dev)**

```bash
cd D:/PlanForge
docker compose up db -d
```

Expected: PostgreSQL running on `localhost:5432`. Verify:
```bash
docker compose ps
```

**Step 6: Commit**

```bash
cd D:/PlanForge
git add docker-compose.yml backend/Dockerfile frontend/Dockerfile backend/.env.example
git commit -m "feat: add Docker Compose with postgres, backend, frontend services"
```

---

## Task 5: Backend Database Connection (Async SQLAlchemy)

**Files:**
- Create: `backend/app/db.py`
- Create: `backend/app/config/settings.py`

**Step 1: Create `backend/app/config/settings.py`**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://planforge:planforge@localhost:5432/planforge"

    class Config:
        env_file = ".env"

settings = Settings()
```

**Step 2: Create `backend/app/db.py`**

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config.settings import settings

engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
```

**Step 3: Write a test that the engine is configured correctly**

Add to `backend/tests/test_health.py`:
```python
from app.db import engine

def test_engine_is_configured():
    assert "planforge" in str(engine.url)
```

**Step 4: Run tests**

```bash
cd D:/PlanForge/backend
uv run pytest -v
```

Expected: Both tests pass.

**Step 5: Commit**

```bash
cd D:/PlanForge
git add backend/app/db.py backend/app/config/settings.py
git commit -m "feat: add async SQLAlchemy engine and settings config"
```

---

## Task 6: Verify Full Local Dev Workflow

**Step 1: Start DB via Docker**

```bash
cd D:/PlanForge
docker compose up db -d
```

**Step 2: Start backend**

```bash
cd D:/PlanForge/backend
uv run uvicorn app.main:app --reload --port 8000
```

**Step 3: Start frontend (new terminal)**

```bash
cd D:/PlanForge/frontend
npm run dev
```

**Step 4: Verify endpoints**

- `http://localhost:3000` → PlanForge heading
- `http://localhost:8000/api/health` → `{"status":"ok"}`
- `http://localhost:8000/docs` → Swagger UI

**Step 5: Run all backend tests**

```bash
cd D:/PlanForge/backend
uv run pytest -v
```

Expected: All pass.

**Step 6: Final commit**

```bash
cd D:/PlanForge
git add .
git commit -m "chore: verify full local dev workflow — scaffold complete"
```

---

## Done: Scaffold Complete

At this point you have:
- Git repo initialized
- `backend/` — FastAPI + uv + Shapely + ReportLab + compliance config JSON
- `frontend/` — Next.js 15 + TypeScript + Tailwind + Better Auth installed
- `docker-compose.yml` — postgres + backend + frontend
- DB connection layer (async SQLAlchemy)
- Health check endpoint with passing test

**Next step:** Better Auth setup (user registration + login + session management)
