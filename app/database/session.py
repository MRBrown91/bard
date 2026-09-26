"""Database engine and session configuration."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


def _async_database_url(url: str) -> str:
    """Convert a synchronous PostgreSQL URL into an async psycopg URL."""
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql+psycopg://", 1)
    return url


engine = create_async_engine(_async_database_url(settings.database_url), future=True)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an application database session."""
    async with SessionFactory() as session:
        yield session
