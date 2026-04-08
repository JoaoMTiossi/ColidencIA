"""
Configuração do banco de dados SQLite com SQLAlchemy async.
"""
from __future__ import annotations

import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from .config import DATABASE_URL

# Converter URL síncrona em assíncrona (sqlite → sqlite+aiosqlite)
_async_url = DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///")

engine = create_async_engine(_async_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """Cria todas as tabelas se não existirem."""
    # Garantir que o diretório do banco existe
    db_path = DATABASE_URL.replace("sqlite:///", "")
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    async with engine.begin() as conn:
        from . import models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """Dependency injection para FastAPI."""
    async with AsyncSessionLocal() as session:
        yield session
