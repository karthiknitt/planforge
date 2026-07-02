from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config.settings import settings


def build_engine_kwargs(use_nullpool: bool) -> dict:
    kwargs: dict = {"echo": False}
    if use_nullpool:
        kwargs["poolclass"] = NullPool
    return kwargs


engine = create_async_engine(
    settings.database_url, **build_engine_kwargs(settings.db_use_nullpool)
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
