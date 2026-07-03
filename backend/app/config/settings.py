from pydantic import ConfigDict
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


settings = Settings()
