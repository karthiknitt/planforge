"""Inngest client + durable functions.

Scope guard (phase-0 plan §4-3e): Inngest wraps ONLY layout generation and
AI renders. The executor invokes /api/inngest over HTTP, so the solve runs
inside a normal Cloud Run request lifecycle (full CPU) — no
--cpu-always-allocated needed.
"""

import inngest

from app.config.settings import settings
from app.services import jobs, render_runner

inngest_client = inngest.Inngest(
    app_id=settings.inngest_app_id,
    event_key=settings.inngest_event_key or None,
    signing_key=settings.inngest_signing_key or None,
    is_production=bool(settings.inngest_signing_key),
)


def inngest_enabled() -> bool:
    return bool(settings.inngest_event_key and settings.inngest_signing_key)


@inngest_client.create_function(
    fn_id="layout-generate",
    trigger=inngest.TriggerEvent(event="layout/generate.requested"),
    retries=2,
)
async def layout_generate(ctx: inngest.Context) -> str:
    job_id = ctx.event.data["job_id"]
    await ctx.step.run("solve-and-store", jobs.run_layout_job, job_id)
    return job_id


@inngest_client.create_function(
    fn_id="render-generate",
    trigger=inngest.TriggerEvent(event="render/requested"),
    retries=1,
)
async def render_generate(ctx: inngest.Context) -> str:
    job_id = ctx.event.data["job_id"]
    await ctx.step.run("render-and-store", render_runner.run_render_job, job_id)
    return job_id
