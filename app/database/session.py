"""Database engine and session configuration."""

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


def _async_database_url(url: str) -> str:
    """Convert a synchronous PostgreSQL URL into an async psycopg URL."""
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql+psycopg://", 1)
    return url


engine = create_async_engine(_async_database_url(settings.database_url), future=True)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "connect")
def _set_session_timezone(dbapi_connection: object, _record: object) -> None:
    """Pin each connection to UTC.

    All timestamp columns are ``timestamptz``. Without this, PostgreSQL renders
    them in the server's zone, so identical data would serialise differently
    depending on where the database runs.
    """
    with dbapi_connection.cursor() as cursor:  # type: ignore[attr-defined]
        cursor.execute("SET TIME ZONE 'UTC'")


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an application database session with explicit commit."""
    session = SessionFactory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()