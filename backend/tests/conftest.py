from __future__ import annotations

import os
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Prevent LLM client initialization failures during test imports.
os.environ.setdefault("GEMINI_API_KEY", "test-key")
# Some modules import with `backend.app...`; add repo root to import path for tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.db.base_class import Base
from app.db.session import get_async_session
from app.main import app


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
async def test_db_session_factory(
    tmp_path: Path,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    db_path = tmp_path / "test_backend.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield session_factory
    finally:
        await engine.dispose()


@pytest.fixture()
async def test_app(
    test_db_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator:
    async def _override_get_async_session() -> AsyncGenerator[AsyncSession]:
        async with test_db_session_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = _override_get_async_session
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
async def async_client(test_app) -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
