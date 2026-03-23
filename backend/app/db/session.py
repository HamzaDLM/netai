from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_scoped_session,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import project_settings

DATABASE_URL: str = str(project_settings.SQLALCHEMY_URL)

async_engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False},
)

SessionLocal = async_sessionmaker(bind=async_engine)

AsyncScopedSession = async_scoped_session(SessionLocal, scopefunc=lambda: None)


async def get_async_session() -> AsyncGenerator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def close_engine() -> None:
    await async_engine.dispose()
