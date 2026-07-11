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

    @field_validator("internal_auth_secret")
    @classmethod
    def _secret_min_length(cls, v: str) -> str:
        # HS256 brute-force resistance requires >= 32 bytes (RFC 7518 §3.2).
        # A short secret lets an attacker mint tokens for ANY user_id.
        if len(v) < 32:
            raise ValueError("INTERNAL_AUTH_SECRET must be at least 32 characters")
        return v


settings = Settings()
