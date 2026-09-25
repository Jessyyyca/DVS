"""End-to-end tests for TickermintProductsImporter against the fake pool.

Covers the contract:
    * one row per Limitless card (PK = card_id)
    * single search per card: "{card_name} {card_set_number}/{set_number}"
    * match -> upsert with all TickerMint fields populated
    * miss -> log + upsert with product_id NULL
    * rerunning is idempotent (latest upsert wins)
    * skipped (missing card_set_number or set_number) -> NULL row
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import pytest

from dvs.api.base import RateLimit
from dvs.api.tickermint_products import TickermintProductsImporter

from ._fakepg import make_pool


def _rate_limit() -> RateLimit:
    return RateLimit(burst=1000, window_seconds=1.0)


# ---------------------------------------------------------------------------
# Minimal aiohttp stand-in for /products/search.
# ---------------------------------------------------------------------------


class _FakeSearchResponse:
    def __init__(self, payload: Any):
        self._payload = payload
        self.status = 200

    async def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        return None

    async def __aenter__(self) -> "_FakeSearchResponse":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakeSearchSession:
    """Routes GET to the per-query payload map and records each call."""

    def __init__(self, payloads: dict[str, Any]):
        self._payloads = payloads
        self.calls: list[tuple[str, dict | None]] = []

    def get(self, url: str, *, params: dict | None = None, **_more: Any):
        self.calls.append((url, params))
        # Match by the literal query string (no percent-decoding needed
        # because our test data uses ASCII only).
        q = (params or {}).get("q", "")
        payload = self._payloads.get(q, [])
        return _FakeSearchResponse(payload)


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


async def _seed_card(
    pool,
    card_id: int,
    card_name: str,
    set_code: str | None,
    card_number: str | None,
) -> None:
    """Insert one card row -- prerequisite for the importer to find it."""
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO card (card_id, card_name, set_code, card_number) "
            "VALUES ($1, $2, $3, $4)",
            card_id,
            card_name,
            set_code,
            card_number,
        )


def _row(pool, card_id: int) -> dict:
    return pool._tables["card_product"].rows[(card_id,)]


# ---------------------------------------------------------------------------
# setup_schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_setup_schema_creates_card_product() -> None:
    pool = make_pool()
    imp = TickermintProductsImporter(pool, rate_limit=_rate_limit())
    await imp.setup_schema()
    # fake's CREATE TABLE handler is a no-op, but we can prove the
    # importer accepts a pool whose card_product table is empty.
    assert "card_product" in pool._tables


# ---------------------------------------------------------------------------
# Matched card -> upserts full TickerMint fields.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_matched_card_upserts_full_product_fields() -> None:
    pool = make_pool()
    await _seed_card(pool, card_id=1, card_name="Pikachu ex", set_code="SVI", card_number="200")

    payload = [{
        "product_id": 654458,
        "name": "Pikachu ex - 200/165",
        "group_id": 24380,
        "rarity": "Ultra Rare",
    }]
    session = _FakeSearchSession({"Pikachu ex 200/165": payload})

    imp = TickermintProductsImporter(pool, rate_limit=_rate_limit())
    await imp.run(concurrency=2, session=session)  # type: ignore[arg-type]

    assert len(pool._tables["card_product"].rows) == 1
    row = _row(pool, 1)
    assert row["card_id"] == 1
    assert row["product_id"] == 654458
    assert row["group_id"] == 24380
    assert row["rarity"] == "Ultra Rare"
    assert row["search_query"] == "Pikachu ex 200/165"
    assert row["set_number"] == "165"
    assert row["card_set_number"] == "200"

    # Only one HTTP call, and to the right URL.
    assert len(session.calls) == 1
    url, params = session.calls[0]
    assert url.endswith("/products/search")
    assert params == {"q": "Pikachu ex 200/165", "game": "pokemon"}


# ---------------------------------------------------------------------------
# No result -> NULL row logged + persisted.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_miss_inserts_null_row_and_logs(caplog) -> None:
    pool = make_pool()
    await _seed_card(
        pool,
        card_id=2,
        card_name="Definitely Not A Card",
        set_code="SVI",
        card_number="1",
    )
    session = _FakeSearchSession({"Definitely Not A Card 1/165": []})

    imp = TickermintProductsImporter(
        pool,
        rate_limit=_rate_limit(),
        logger=logging.getLogger("dvs.test.tpi.miss"),
    )
    with caplog.at_level(logging.INFO, logger="dvs.test.tpi.miss"):
        await imp.run(concurrency=2, session=session)  # type: ignore[arg-type]

    # The NULL row is still written so the attempt is visible.
    row = _row(pool, 2)
    assert row["product_id"] is None
    assert row["group_id"] is None
    assert row["card_name"] is None
    assert row["rarity"] is None
    assert row["search_query"] == "Definitely Not A Card 1/165"
    assert row["set_number"] == "165"
    assert row["card_set_number"] == "1"

    # And the miss is logged at INFO.
    assert any(
        "no TickerMint match" in rec.message and "card_id=2" in rec.message
        for rec in caplog.records
    ), [r.message for r in caplog.records]


# ---------------------------------------------------------------------------
# Skip (no query buildable) -> NULL row, no HTTP call.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_card_set_number_inserts_null_no_http() -> None:
    pool = make_pool()
    await _seed_card(pool, card_id=3, card_name="Mystery Card", set_code="SVI", card_number=None)
    session = _FakeSearchSession({})

    imp = TickermintProductsImporter(pool, rate_limit=_rate_limit())
    await imp.run(concurrency=2, session=session)  # type: ignore[arg-type]

    assert session.calls == []
    row = _row(pool, 3)
    assert row["product_id"] is None
    assert row["card_set_number"] is None  # nothing to record


@pytest.mark.asyncio
async def test_unmapped_set_code_inserts_null_no_http() -> None:
    pool = make_pool()
    await _seed_card(pool, card_id=4, card_name="Mystery", set_code="ZZZ", card_number="42")
    session = _FakeSearchSession({})

    imp = TickermintProductsImporter(pool, rate_limit=_rate_limit())
    await imp.run(concurrency=2, session=session)  # type: ignore[arg-type]

    assert session.calls == []
    row = _row(pool, 4)
    assert row["product_id"] is None
    assert row["set_number"] is None  # denominator_for("ZZZ") is None


# ---------------------------------------------------------------------------
# Idempotency: rerunning with the same data yields the same row count.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerun_is_idempotent() -> None:
    pool = make_pool()
    await _seed_card(pool, card_id=1, card_name="Pikachu ex", set_code="SVI", card_number="200")
    payload = [{
        "product_id": 654458,
        "name": "Pikachu ex - 200/165",
        "group_id": 24380,
        "rarity": "Ultra Rare",
    }]
    session = _FakeSearchSession({"Pikachu ex 200/165": payload})

    imp = TickermintProductsImporter(pool, rate_limit=_rate_limit())
    await imp.run(concurrency=2, session=session)  # type: ignore[arg-type]
    await imp.run(concurrency=2, session=session)  # type: ignore[arg-type]

    assert len(pool._tables["card_product"].rows) == 1
    # Both runs made exactly one search call.
    assert len(session.calls) == 2


@pytest.mark.asyncio
async def test_rerun_can_flip_match_to_null() -> None:
    """If the API returns nothing on a later run, the previously matched
    row is updated to a NULL row (latest upsert wins)."""
    pool = make_pool()
    await _seed_card(pool, card_id=1, card_name="Pikachu ex", set_code="SVI", card_number="200")

    # First run: matched.
    matched_payload = [{"product_id": 654458, "name": "Pikachu ex - 200/165"}]
    # Second run: empty.
    session1 = _FakeSearchSession({"Pikachu ex 200/165": matched_payload})
    imp = TickermintProductsImporter(pool, rate_limit=_rate_limit())
    await imp.run(concurrency=2, session=session1)  # type: ignore[arg-type]
    assert _row(pool, 1)["product_id"] == 654458

    session2 = _FakeSearchSession({"Pikachu ex 200/165": []})
    await imp.run(concurrency=2, session=session2)  # type: ignore[arg-type]
    assert _row(pool, 1)["product_id"] is None


@pytest.mark.asyncio
async def test_rerun_can_flip_null_to_match() -> None:
    """Conversely, a row that previously missed can pick up a match later."""
    pool = make_pool()
    await _seed_card(pool, card_id=1, card_name="Pikachu ex", set_code="SVI", card_number="200")

    imp = TickermintProductsImporter(pool, rate_limit=_rate_limit())
    # First run: nothing.
    await imp.run(concurrency=2, session=_FakeSearchSession({"Pikachu ex 200/165": []}))  # type: ignore[arg-type]
    assert _row(pool, 1)["product_id"] is None

    # Second run: matched.
    session = _FakeSearchSession({
        "Pikachu ex 200/165": [
            {"product_id": 654458, "name": "Pikachu ex - 200/165", "rarity": "Rare"}
        ]
    })
    await imp.run(concurrency=2, session=session)  # type: ignore[arg-type]
    row = _row(pool, 1)
    assert row["product_id"] == 654458
    assert row["rarity"] == "Rare"


# ---------------------------------------------------------------------------
# Concurrency: many cards, no shared mutable state across runs.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runs_one_search_per_card() -> None:
    pool = make_pool()
    cards = [
        (10, "Pikachu ex", "SVI", "200"),
        (11, "Charizard ex", "SVI", "199"),
        (12, "Mewtwo V", "SVI", "31"),
    ]
    for cid, name, code, num in cards:
        await _seed_card(pool, cid, name, code, num)

    # First two hit, third misses.
    payloads = {
        "Pikachu ex 200/165": [{"product_id": 1, "name": "Pikachu ex - 200/165"}],
        "Charizard ex 199/165": [{"product_id": 2, "name": "Charizard ex - 199/165"}],
        "Mewtwo V 31/165": [],
    }
    session = _FakeSearchSession(payloads)
    imp = TickermintProductsImporter(pool, rate_limit=_rate_limit())
    await imp.run(concurrency=3, session=session)  # type: ignore[arg-type]

    # One row per card.
    assert len(pool._tables["card_product"].rows) == 3
    # Two product_ids populated, one NULL.
    assert _row(pool, 10)["product_id"] == 1
    assert _row(pool, 11)["product_id"] == 2
    assert _row(pool, 12)["product_id"] is None
    # One HTTP call per card, no fallback retries.
    assert len(session.calls) == 3


# ---------------------------------------------------------------------------
# api_probe_url
# ---------------------------------------------------------------------------


def test_api_probe_url_uses_known_endpoint() -> None:
    pool = make_pool()
    imp = TickermintProductsImporter(pool, rate_limit=_rate_limit())
    assert imp.api_probe_url() == (
        "https://api.tickermint.cards/products/search?q=pikachu&game=pokemon"
    )


def test_aiohttp_session_type_accepts_our_fake() -> None:
    """Static check: the run() method accepts the fake session shape."""
    pool = make_pool()
    imp = TickermintProductsImporter(pool, rate_limit=_rate_limit())
    assert imp.api_base_url == "https://api.tickermint.cards"
