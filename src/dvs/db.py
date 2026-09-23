"""asyncpg pool singleton for the DVS importers."""

from __future__ import annotations

import logging

import asyncpg

from .config import get_dsn

_log = logging.getLogger("dvs.db")
_pool: asyncpg.Pool | None = None


async def get_pool(min_size: int = 2, max_size: int = 10) -> asyncpg.Pool:
    """Return a process-wide asyncpg pool, creating it on first call."""
    global _pool
    if _pool is None:
        _log.info("creating asyncpg pool min=%d max=%d", min_size, max_size)
        _pool = await asyncpg.create_pool(
            get_dsn(), min_size=min_size, max_size=max_size
        )
    return _pool


async def close_pool() -> None:
    """Close the pool if one exists. Safe to call from CLI teardown."""
    global _pool
    if _pool is not None:
        _log.info("closing asyncpg pool")
        await _pool.close()
        _pool = None


async def ping(pool: asyncpg.Pool | None = None) -> None:
    """Round-trip SELECT 1 against the pool to prove DB connectivity."""
    p = pool or await get_pool()
    async with p.acquire() as conn:
        result = await conn.fetchval("SELECT 1")
        if result != 1:
            raise RuntimeError(f"unexpected SELECT 1 result: {result!r}")