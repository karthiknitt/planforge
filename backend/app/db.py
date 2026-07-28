import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config.settings import settings

logger = logging.getLogger(__name__)


def is_pooled_url(url: str) -> bool:
    """True if the URL points at Neon's PgBouncer endpoint."""
    return "-pooler." in url


def build_engine_kwargs(use_nullpool: bool) -> dict:
    kwargs: dict = {"echo": False}
    if use_nullpool:
        kwargs["poolclass"] = NullPool
    return kwargs


engine = create_async_engine(
    settings.database_url, **build_engine_kwargs(settings.db_use_nullpool)
)

if settings.db_use_nullpool and not is_pooled_url(settings.database_url):
    logger.warning(
        "DB_USE_NULLPOOL is on but DATABASE_URL is not Neon's pooled endpoint. "
        "Every request will open a new TLS connection and Neon's connection "
        "cap becomes the scaling ceiling. Use the '-pooler' hostname."
    )

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
