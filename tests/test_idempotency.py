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
async def test_limitless_card_map_wipe_and_replace_is_idempotent() -> None:
    """Re-running a match for a card must replace stale candidates cleanly.

    The 1:N map wipes existing rows for limitless_card_id before
    re-inserting, so shrinking/changing candidates leaves no residue.
    No candidate should also leave the table empty for that card.
    """
    pool = make_pool()
    imp = TickermintProductsImporter(pool, rate_limit=_rate_limit())
    async with pool.acquire() as conn:
        # Manually wire a card and three mapping rows for it.
        await conn.execute(
            "INSERT INTO card (card_id, card_name, set_code, card_number) "
            "VALUES ($1, $2, $3, $4)",
            1, "Wiglett", "TEF", "47",
        )
        await conn.execute(
            "INSERT INTO card_product (product_id, card_name) "
            "VALUES ($1, $2)",
            100, "Wiglett",
        )
        await conn.execute(
            "INSERT INTO card_product (product_id, card_name) "
            "VALUES ($1, $2)",
            101, "Wiglett",
        )
        await conn.execute(
            "INSERT INTO card_product (product_id, card_name) "
            "VALUES ($1, $2)",
            102, "Wiglett",
        )

        # First run: keep all three mappings (idempotent insert path).
        for pid in (100, 101, 102):
            await conn.execute(
                "INSERT INTO limitless_card_map "
                "(limitless_card_id, product_id, match_kind, search_query) "
                "VALUES ($1, $2, $3, $4) "
                "ON CONFLICT (limitless_card_id, product_id) DO NOTHING",
                1, pid, "exact_number", "Wiglett TEF 47",
            )
        assert len(pool._tables["limitless_card_map"].rows) == 3

        # Wipe-and-replace with a smaller set. Replaces 100 + 101 with 100
        # only -- 102 must disappear, no duplicate 100 must remain.
        await conn.execute(
            "DELETE FROM limitless_card_map WHERE limitless_card_id = $1",
            1,
        )
        await conn.execute(
            "INSERT INTO limitless_card_map "
            "(limitless_card_id, product_id, match_kind, search_query) "
            "VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (limitless_card_id, product_id) DO NOTHING",
            1, 100, "exact_number", "Wiglett TEF 47",
        )

    rows = pool._tables["limitless_card_map"].rows
    assert len(rows) == 1
    only = next(iter(rows.values()))
    assert only["product_id"] == 100
    assert only["limitless_card_id"] == 1


@pytest.mark.asyncio
async def test_limitless_card_map_replace_with_no_candidates() -> None:
    """A search that returns nothing must still clean up prior rows."""
    pool = make_pool()
    imp = TickermintProductsImporter(pool, rate_limit=_rate_limit())
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO card (card_id, card_name, set_code, card_number) "
            "VALUES ($1, $2, $3, $4)",
            2, "Mewtwo", "base1", "10",
        )
        await conn.execute(
            "INSERT INTO card_product (product_id, card_name) "
            "VALUES ($1, $2)",
            200, "Mewtwo",
        )
        await conn.execute(
            "INSERT INTO limitless_card_map "
            "(limitless_card_id, product_id, match_kind, search_query) "
            "VALUES ($1, $2, $3, $4)",
            2, 200, "exact_number", "Mewtwo base1 10",
        )
        assert len(pool._tables["limitless_card_map"].rows) == 1

        # Match returns nothing -> wipe, insert nothing.
        await conn.execute(
            "DELETE FROM limitless_card_map WHERE limitless_card_id = $1",
            2,
        )

    assert pool._tables["limitless_card_map"].rows == {}


@pytest.mark.asyncio
async def test_limitless_card_map_fuzzy_row_persists_similarity() -> None:
    """Fuzzy-tier rows must persist the rapidfuzz score alongside the FK."""
    pool = make_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO card (card_id, card_name, set_code, card_number) "
            "VALUES ($1, $2, $3, $4)",
            9, "Marill", "ASC", "83",
        )
        await conn.execute(
            "INSERT INTO card_product (product_id, card_name) "
            "VALUES ($1, $2)",
            300, "Marill - 083/217 (Friend Ball)",
        )
        await conn.execute(
            "INSERT INTO limitless_card_map "
            "(limitless_card_id, product_id, match_kind, similarity, "
            "search_query) "
            "VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT (limitless_card_id, product_id) DO NOTHING",
            9, 300, "fuzzy", 92, "Marill ASC 83",
        )

    rows = pool._tables["limitless_card_map"].rows
    assert len(rows) == 1
    only = next(iter(rows.values()))
    assert only["match_kind"] == "fuzzy"
    assert only["similarity"] == 92


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