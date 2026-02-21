# PlanForge

> G+1 residential floor plan generator for Indian small builders and civil engineers.

PlanForge takes plot dimensions, setbacks, and room preferences and instantly generates three compliant layout variations — complete with SVG preview, section view, Bill of Quantities, PDF drawing, and DXF export.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js)
![FastAPI](https://img.shields.io/badge/FastAPI-0.129-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-blue)

---

## Quick Start

**Prerequisites:** Docker, Node.js 20+, Python 3.12+, [uv](https://astral.sh/uv)

```bash
# Configure
cp frontend/.env.local.example frontend/.env.local   # fill in secrets

# Install
npm install --prefix frontend
cd backend && uv sync

# Run
./dev-start.sh
```

App → `http://localhost:3001`
API docs → `http://localhost:8002/docs`

**First run only** — push the auth schema:
```bash
cd frontend
DATABASE_URL="postgresql://planforge:planforge@localhost:5432/planforge" \
  npx drizzle-kit push
```

---

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind v4, ShadCN, Better Auth |
| Backend | FastAPI, SQLAlchemy async, Shapely, OR-Tools CP-SAT |
| Database | PostgreSQL 16 |
| PDF / DXF | ReportLab, ezdxf |
| Payments | Razorpay |
| Tooling | Biome, Drizzle ORM, uv |

---

## Documentation

**[docs/developer-reference.md](docs/developer-reference.md)** — full architecture, API reference, engine internals, DB schema, feature gating, testing guide, and UI system.

---

## License

MIT © Karthikeyan Natarajan
