from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://planforge:planforge@localhost:5432/planforge"

    class Config:
        env_file = ".env"


settings = Settings()
