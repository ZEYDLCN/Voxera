from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from voxera.core.config import Settings


class Database:
    """Own the async engine and transaction-scoped SQLAlchemy sessions."""

    def __init__(self, settings: Settings) -> None:
        self._engine = create_async_engine(
            settings.database_url,
            echo=settings.database_echo,
            pool_pre_ping=True,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout_seconds,
        )
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @asynccontextmanager
    async def session(self, organization_id: UUID | None = None) -> AsyncIterator[AsyncSession]:
        """Open one transaction, optionally scoped by PostgreSQL tenant context."""

        async with self._session_factory() as session, session.begin():
            if organization_id is not None:
                await session.execute(
                    text(
                        "SELECT set_config("
                        "'app.current_organization_id', :organization_id, true)"
                    ),
                    {"organization_id": str(organization_id)},
                )
            yield session

    async def ping(self) -> None:
        async with self._engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        await self._engine.dispose()
