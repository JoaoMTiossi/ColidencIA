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
    """Cria tabelas se não existirem e aplica migrações de colunas novas."""
    db_path = DATABASE_URL.replace("sqlite:///", "")
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    async with engine.begin() as conn:
        from . import models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
        # Migração incremental: adiciona colunas novas sem recriar o banco
        await conn.run_sync(_migrar_colunas)


def _migrar_colunas(conn) -> None:
    """Adiciona colunas novas via ALTER TABLE quando ainda não existem (SQLite)."""
    from sqlalchemy import inspect, text
    insp = inspect(conn)
    cols_existentes = {c["name"] for c in insp.get_columns("resultados")}
    novas = [
        ("processo_base", "VARCHAR(50)"),
        ("ncl_versao_base", "INTEGER"),
        ("titular_base", "VARCHAR(500)"),
    ]
    for col, tipo in novas:
        if col not in cols_existentes:
            conn.execute(text(f"ALTER TABLE resultados ADD COLUMN {col} {tipo}"))


async def get_db():
    """Dependency injection para FastAPI."""
    async with AsyncSessionLocal() as session:
        yield session
