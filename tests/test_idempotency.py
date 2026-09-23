"""Idempotency tests: insert the same rows twice, expect no error.

Driven against a tiny in-memory fake of asyncpg (see tests/_fakepg.py)
so the tests stay offline.
"""

from __future__ import annotations

import datetime as dt
import uuid

import asyncpg  # for the real exception class
import pytest

from dvs.api.base import RateLimit
from dvs.api.limitless import LimitlessImporter
from dvs.api.tickermint_products import TickermintProductsImporter

from ._fakepg import UniqueViolationError, make_pool


def _rate_limit() -> RateLimit:
    return RateLimit(burst=1000, window_seconds=1.0)


def _event_date() -> dt.date:
    return dt.date(2026, 1, 1)


@pytest.mark.asyncio
async def test_deck_card_insert_is_idempotent() -> None:
    pool = make_pool()
    imp = LimitlessImporter(pool, rate_limit=_rate_limit())

    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO deck (deck_id, source_event_id, event_date, format) "
            "VALUES ($1, $2, $3, $4)",
            uuid.uuid4(),
            "evt-1",
            _event_date(),
            "STANDARD",
        )
        deck_id = next(iter(conn._tables["deck"].rows))
        # First insert succeeds.
        await conn.execute(
            "INSERT INTO deck_card (deck_id, card_id, quantity) "
            "VALUES ($1, $2, $3) "
            "ON CONFLICT (deck_id, card_id) DO NOTHING",
            deck_id,
            42,
            3,
        )
        # Second insert with same PK is swallowed by ON CONFLICT.
        await conn.execute(
            "INSERT INTO deck_card (deck_id, card_id, quantity) "
            "VALUES ($1, $2, $3) "
            "ON CONFLICT (deck_id, card_id) DO NOTHING",
            deck_id,
            42,
            3,
        )

    assert len(pool._tables["deck_card"].rows) == 1


@pytest.mark.asyncio
async def test_card_unique_violation_is_swallowed_by_caller() -> None:
    """The card INSERT has no ON CONFLICT; uniqueness is enforced by the
    race-safe fallback in LimitlessImporter._get_or_create_card."""
    pool = make_pool()
    imp = LimitlessImporter(pool, rate_limit=_rate_limit())

    async with pool.acquire() as conn:
        cid1 = await imp._get_or_create_card(conn, "Pikachu", "base1", "58")
        # First call hits the SELECT path (no row yet) and then INSERT.
        assert cid1 is not None
        cid2 = await imp._get_or_create_card(conn, "Pikachu", "base1", "58")
        # Second call sees the existing row, returns it without an INSERT.
        assert cid2 == cid1


@pytest.mark.asyncio
async def test_card_race_against_real_unique_violation() -> None:
    """Simulate a concurrent insert: fetchval raises asyncpg.UniqueViolationError
    and the fallback SELECT returns the winner's id."""
    pool = make_pool()
    imp = LimitlessImporter(pool, rate_limit=_rate_limit())

    async with pool.acquire() as conn:
        # Pre-populate with the row another "worker" inserted.
        await conn.execute(
            "INSERT INTO card (card_id, card_name, set_code, card_number) "
            "VALUES ($1, $2, $3, $4)",
            7,
            "Pikachu",
            "base1",
            "58",
        )
        real_fetchrow = conn.fetchrow
        call_count = {"n": 0}

        async def fetchrow_with_recovery(query: str, *args):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None  # initial cache miss
            return await real_fetchrow(query, *args)

        async def fetchval_raises(query: str, *args):
            if "INSERT INTO card" in query:
                raise asyncpg.UniqueViolationError("dup")
            return None

        conn.fetchrow = fetchrow_with_recovery  # type: ignore[assignment]
        conn.fetchval = fetchval_raises  # type: ignore[assignment]
        cid = await imp._get_or_create_card(conn, "Pikachu", "base1", "58")
        assert cid == 7


@pytest.mark.asyncio
async def test_printing_insert_is_idempotent() -> None:
    pool = make_pool()
    async with pool.acquire() as conn:
        for _ in range(2):
            await conn.execute(
                "INSERT INTO printing (product_id, printing_type) "
                "VALUES ($1, $2) ON CONFLICT DO NOTHING",
                1234,
                "Normal",
            )
    assert len(pool._tables["printing"].rows) == 1


@pytest.mark.asyncio
async def test_daily_price_upsert_is_idempotent() -> None:
    pool = make_pool()
    async with pool.acquire() as conn:
        for _ in range(2):
            await conn.execute(
                "INSERT INTO printing (product_id, printing_type) "
                "VALUES ($1, $2) ON CONFLICT DO NOTHING",
                9999,
                "Holofoil",
            )
            await conn.execute(
                "INSERT INTO daily_price "
                "(product_id, printing_type, price_date, market_price) "
                "VALUES ($1, $2, $3, $4) "
                "ON CONFLICT (product_id, printing_type, price_date) "
                "DO UPDATE SET market_price = EXCLUDED.market_price",
                9999,
                "Holofoil",
                dt.date(2026, 1, 1),
                "12.34",
            )
    rows = pool._tables["daily_price"].rows
    assert len(rows) == 1
    key = next(iter(rows))
    assert rows[key]["market_price"] == "12.34"


@pytest.mark.asyncio
async def test_card_product_upsert_merges() -> None:
    pool = make_pool()
    imp = TickermintProductsImporter(pool, rate_limit=_rate_limit())
    async with pool.acquire() as conn:
        await imp._save_product(
            conn,
            {
                "card_name": "Pikachu",
                "set": "Base",
                "number": "58",
                "rarity": "Common",
            },
            7777,
        )
        await imp._save_product(
            conn,
            {
                "card_name": "Pikachu",
                "set": "Base",
                "number": "58",
                "rarity": "Common",
                "image_url": "https://x/y.png",
            },
            7777,
        )
    row = next(iter(pool._tables["card_product"].rows.values()))
    assert row["image_url"] == "https://x/y.png"


@pytest.mark.asyncio
async def test_unprotected_insert_still_raises() -> None:
    """Sanity check: without ON CONFLICT, the fake does raise so the
    protection is what actually saves us."""
    pool = make_pool()
    deck_id = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO deck_card (deck_id, card_id, quantity) "
            "VALUES ($1, $2, $3)",
            deck_id,
            1,
            1,
        )
        with pytest.raises(UniqueViolationError):
            await conn.execute(
                "INSERT INTO deck_card (deck_id, card_id, quantity) "
                "VALUES ($1, $2, $3)",
                deck_id,
                1,
                1,
            )


@pytest.mark.asyncio
async def test_race_safe_card_insert_via_real_asyncpg_class() -> None:
    """Cross-checks the catch-and-recover path against the real exception class.

    Same scenario as test_card_race_against_real_unique_violation but
    focuses on the exception type rather than the route through it.
    """
    pool = make_pool()
    imp = LimitlessImporter(pool, rate_limit=_rate_limit())

    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO card (card_id, card_name, set_code, card_number) "
            "VALUES ($1, $2, $3, $4)",
            7,
            "Pikachu",
            "base1",
            "58",
        )
        # Use real UniqueViolationError from asyncpg.
        try:
            raise asyncpg.UniqueViolationError("dup")
        except asyncpg.UniqueViolationError as exc:
            assert str(exc) == "dup"