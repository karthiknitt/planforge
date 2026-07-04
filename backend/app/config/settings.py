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

    @field_validator("internal_auth_secret")
    @classmethod
    def _secret_min_length(cls, v: str) -> str:
        # HS256 brute-force resistance requires >= 32 bytes (RFC 7518 §3.2).
        # A short secret lets an attacker mint tokens for ANY user_id.
        if len(v) < 32:
            raise ValueError("INTERNAL_AUTH_SECRET must be at least 32 characters")
        return v


settings = Settings()
