import math
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    export,
    gallery,
    generate,
    health,
    jobs,
    payments,
    projects,
    render,
    revisions,
    rooms,
    share,
    teams,
)
from app.config.cors import parse_allowed_origins
from app.config.settings import settings
from app.db import Base, engine
from app.auto_migrate import auto_migrate_missing_columns

# Import all models so SQLAlchemy knows about them before create_all
import app.models.job  # noqa: F401
import app.models.layout  # noqa: F401
import app.models.payment  # noqa: F401
import app.models.project  # noqa: F401
import app.models.render  # noqa: F401
import app.models.revision  # noqa: F401
import app.models.team  # noqa: F401
import app.models.user  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await auto_migrate_missing_columns(engine)
    yield


app = FastAPI(title="PlanForge API", version="0.1.0", lifespan=lifespan)


def _json_safe(o):
    """Make a validation-error payload JSON-serializable. The default handler
    echoes the offending input, and a NaN/Infinity input crashes the JSON
    encoder — turning a 422 into a 500."""
    if isinstance(o, float):
        return o if math.isfinite(o) else str(o)
    if isinstance(o, (str, int, bool)) or o is None:
        return o
    if isinstance(o, dict):
        return {str(k): _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_safe(v) for v in o]
    return str(o)


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": _json_safe(exc.errors())})


default_origins = ["http://localhost:3001", "http://localhost:3000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=default_origins + parse_allowed_origins(settings.allowed_origins),
    allow_origin_regex=r"^https://planforge-[a-z0-9-]+-karthikeyan-natarajans-projects\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(gallery.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(generate.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(payments.router, prefix="/api")
app.include_router(rooms.router, prefix="/api")
app.include_router(share.router, prefix="/api")
app.include_router(revisions.router, prefix="/api")
app.include_router(teams.router, prefix="/api")
app.include_router(render.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")

import inngest.fast_api  # noqa: E402

from app.inngest_app import inngest_client, layout_generate, render_generate  # noqa: E402

inngest.fast_api.serve(app, inngest_client, [layout_generate, render_generate])
