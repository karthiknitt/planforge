from pydantic import ConfigDict, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")

    database_url: str = (
        "postgresql+asyncpg://planforge:planforge@localhost:5432/planforge"
    )
    db_use_nullpool: bool = False
    internal_auth_secret: str
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    allowed_origins: str = ""

    # AI render layer (Phase 2) — all optional; provider picked at bake-off
    render_provider: str = ""
    render_model: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""
    openrouter_api_key: str = ""

    # StructAgent structural-design API (structapi) — empty => feature off,
    # the /structural endpoint returns 503 with a clear message.
    structural_api_url: str = ""
    structural_api_key: str = ""

    # Async job pipeline (Phase 3) — both empty => inline synchronous fallback
    inngest_event_key: str = ""
    inngest_signing_key: str = ""
    # Must be distinct per deployment (main vs v2) — Inngest ties function
    # registration to this name, so two deployments sharing one app_id race
    # for which URL actually receives invocations.
    inngest_app_id: str = "planforge"
    # Watchdog (Task 1.5): if a job is still `queued` past this many seconds
    # (e.g. the Inngest app isn't synced to the current deployment URL and
    # the enqueued event is never picked up), the next GET poll fails it
    # fast instead of leaving it queued forever.
    job_queued_timeout_s: int = 120

    # Rate limiting — in-process token bucket (see app/middleware/rate_limit.py)
    rate_limit_capacity: int = 10
    rate_limit_refill_per_second: float = 0.2

    # Cloudflare R2 artifact storage — all four empty => NullStorage (no-op).
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""
    # "inline" streams bytes (today's contract). "redirect" 307s to a signed
    # R2 URL — flip only after verifying the frontend download path.
    export_delivery_mode: str = "inline"
    # Concurrent PDF/DXF renders per instance. ReportLab builds in memory and
    # Cloud Run's filesystem is RAM-backed, so this is the real OOM guard.
    export_max_concurrency: int = 2

    @field_validator("internal_auth_secret")
    @classmethod
    def _secret_min_length(cls, v: str) -> str:
        # HS256 brute-force resistance requires >= 32 bytes (RFC 7518 §3.2).
        # A short secret lets an attacker mint tokens for ANY user_id.
        if len(v) < 32:
            raise ValueError("INTERNAL_AUTH_SECRET must be at least 32 characters")
        return v


settings = Settings()
