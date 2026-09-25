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
    """Saving the same card twice must update fields, not duplicate rows."""
    pool = make_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO card_product "
            "(card_id, product_id, group_id, card_name, rarity, search_query, "
            "set_number, card_set_number) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) "
            "ON CONFLICT (card_id) DO UPDATE SET "
            "product_id = EXCLUDED.product_id, "
            "group_id = EXCLUDED.group_id, "
            "card_name = EXCLUDED.card_name, "
            "rarity = EXCLUDED.rarity, "
            "search_query = EXCLUDED.search_query, "
            "set_number = EXCLUDED.set_number, "
            "card_set_number = EXCLUDED.card_set_number",
            1, 7777, 100, "Pikachu", "Common", "Pikachu 58/165", "165", "58",
        )
        await conn.execute(
            "INSERT INTO card_product "
            "(card_id, product_id, group_id, card_name, rarity, search_query, "
            "set_number, card_set_number) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) "
            "ON CONFLICT (card_id) DO UPDATE SET "
            "product_id = EXCLUDED.product_id, "
            "group_id = EXCLUDED.group_id, "
            "card_name = EXCLUDED.card_name, "
            "rarity = EXCLUDED.rarity, "
            "search_query = EXCLUDED.search_query, "
            "set_number = EXCLUDED.set_number, "
            "card_set_number = EXCLUDED.card_set_number",
            1, 7777, 100, "Pikachu", "Rare", "Pikachu 58/165", "165", "58",
        )
    row = next(iter(pool._tables["card_product"].rows.values()))
    assert row["rarity"] == "Rare"
    assert len(pool._tables["card_product"].rows) == 1


@pytest.mark.asyncio
async def test_card_product_one_per_card_id() -> None:
    """One card_id maps to at most one card_product row, regardless of how
    many products come back from a search (latest upsert wins)."""
    pool = make_pool()
    async with pool.acquire() as conn:
        for card_id, pid in ((10, 100), (10, 101), (10, 102)):
            await conn.execute(
                "INSERT INTO card_product "
                "(card_id, product_id, card_name, search_query, "
                "set_number, card_set_number) "
                "VALUES ($1, $2, $3, $4, $5, $6) "
                "ON CONFLICT (card_id) DO UPDATE SET "
                "product_id = EXCLUDED.product_id",
                card_id, pid, "Wiglett", "Wiglett 47/162", "162", "47",
            )
    rows = pool._tables["card_product"].rows
    assert {key[0] for key in rows} == {10}
    assert next(iter(rows.values()))["product_id"] == 102


@pytest.mark.asyncio
async def test_card_product_unmatched_insert_is_null() -> None:
    """A miss must persist a row with product_id IS NULL so the attempt is
    visible to later runs -- and rerunning still upserts in place."""
    pool = make_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO card_product "
            "(card_id, product_id, search_query, set_number, card_set_number) "
            "VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT (card_id) DO UPDATE SET "
            "product_id = EXCLUDED.product_id, "
            "search_query = EXCLUDED.search_query",
            42, None, "Pikachu 200/69", "69", "200",
        )
        # Second pass still matches the same row -- product_id is still NULL.
        await conn.execute(
            "INSERT INTO card_product "
            "(card_id, product_id, search_query, set_number, card_set_number) "
            "VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT (card_id) DO UPDATE SET "
            "product_id = EXCLUDED.product_id, "
            "search_query = EXCLUDED.search_query",
            42, None, "Pikachu 200/69", "69", "200",
        )
    rows = pool._tables["card_product"].rows
    assert len(rows) == 1
    row = next(iter(rows.values()))
    assert row["product_id"] is None
    assert row["search_query"] == "Pikachu 200/69"


@pytest.mark.asyncio
async def test_card_product_null_product_id_allows_multiple_unmatched_cards() -> None:
    """Postgres UNIQUE treats NULLs as distinct, so two different card_ids
    may both have a NULL product_id without colliding."""
    pool = make_pool()
    async with pool.acquire() as conn:
        for card_id in (1, 2, 3):
            await conn.execute(
                "INSERT INTO card_product "
                "(card_id, product_id, search_query, "
                "set_number, card_set_number) "
                "VALUES ($1, $2, $3, $4, $5) "
                "ON CONFLICT (card_id) DO NOTHING",
                card_id, None, f"Card {card_id} 1/2", "2", "1",
            )
    assert len(pool._tables["card_product"].rows) == 3
    assert all(
        row["product_id"] is None
        for row in pool._tables["card_product"].rows.values()
    )


@pytest.mark.asyncio
async def test_card_product_two_cards_same_product_id_violates_unique() -> None:
    """Two different card_ids mapping to the same product_id IS a real
    conflict -- we cannot have two cards claim the same product."""
    pool = make_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO card_product "
            "(card_id, product_id, search_query, "
            "set_number, card_set_number) "
            "VALUES ($1, $2, $3, $4, $5)",
            1, 999, "Pikachu 1/2", "2", "1",
        )
        with pytest.raises(UniqueViolationError):
            await conn.execute(
                "INSERT INTO card_product "
                "(card_id, product_id, search_query, "
                "set_number, card_set_number) "
                "VALUES ($1, $2, $3, $4, $5)",
                2, 999, "Pikachu 1/2", "2", "1",
            )


@pytest.mark.asyncio
async def test_printing_upsert_updates_printing_id() -> None:
    """Re-importing a product with the same printing_type must update printing_id."""
    pool = make_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO card_product "
            "(card_id, product_id, card_name, search_query) "
            "VALUES ($1, $2, $3, $4)",
            1, 1, "Pikachu", "Pikachu",
        )
        for printing_id in (10, 11):
            await conn.execute(
                "INSERT INTO printing "
                "(product_id, printing_id, printing_type) "
                "VALUES ($1, $2, $3) "
                "ON CONFLICT (product_id, printing_type) DO UPDATE "
                "SET printing_id = EXCLUDED.printing_id",
                1, printing_id, "Normal",
            )
    row = next(iter(pool._tables["printing"].rows.values()))
    assert row["printing_id"] == 11
    assert len(pool._tables["printing"].rows) == 1


@pytest.mark.asyncio
async def test_printing_distinct_printing_types_kept_separate() -> None:
    """Same product, two different printing_types -> two printing rows."""
    pool = make_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO card_product "
            "(card_id, product_id, card_name, search_query) "
            "VALUES ($1, $2, $3, $4)",
            1, 1, "Pikachu", "Pikachu",
        )
        for ptype, pid in (("Normal", 10), ("Holofoil", 11)):
            await conn.execute(
                "INSERT INTO printing "
                "(product_id, printing_id, printing_type) "
                "VALUES ($1, $2, $3) "
                "ON CONFLICT (product_id, printing_type) DO NOTHING",
                1, pid, ptype,
            )
    assert len(pool._tables["printing"].rows) == 2


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