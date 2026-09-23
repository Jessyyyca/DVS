"""Import TickerMint historical prices for matched products (was 03_...)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import aiohttp

from .base import ApiImporter

API_BASE = "https://api.tickermint.cards"

DDL = """
CREATE TABLE IF NOT EXISTS printing (
    product_id BIGINT NOT NULL REFERENCES card_product(product_id) ON DELETE CASCADE,
    printing_type TEXT NOT NULL,
    PRIMARY KEY (product_id, printing_type)
);

CREATE TABLE IF NOT EXISTS daily_price (
    product_id BIGINT NOT NULL,
    printing_type TEXT NOT NULL,
    price_date DATE NOT NULL,
    market_price NUMERIC(12, 4) NOT NULL CHECK (market_price >= 0),
    PRIMARY KEY (product_id, printing_type, price_date),
    FOREIGN KEY (product_id, printing_type)
        REFERENCES printing(product_id, printing_type) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_daily_price_date ON daily_price (price_date);
"""

DATE_KEYS = ("date", "price_date", "priceDate", "day", "snapshot_date")
PRICE_KEYS = ("market_price", "marketPrice", "market", "price")
PRINTING_KEYS = (
    "printing",
    "printing_type",
    "printingType",
    "variant",
    "subtype",
    "finish",
)


def first(obj: dict, keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in obj and obj[key] not in (None, ""):
            return obj[key]
    return None


def maybe_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def maybe_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def looks_like_printing_label(key: str) -> bool:
    k = key.lower().replace("_", " ").replace("-", " ")
    labels = (
        "normal",
        "holo",
        "holofoil",
        "reverse holo",
        "reverse holofoil",
        "foil",
        "non holo",
        "nonholo",
        "1st edition",
        "unlimited",
    )
    return any(label == k or label in k for label in labels)


def iter_price_rows(
    node: Any,
    inherited_printing: str | None = None,
) -> Iterable[tuple[str, date, Decimal]]:
    """Walk both flat and printing-grouped price payloads."""
    if isinstance(node, list):
        for item in node:
            yield from iter_price_rows(item, inherited_printing)
        return
    if not isinstance(node, dict):
        return
    d = maybe_date(first(node, DATE_KEYS))
    p = maybe_decimal(first(node, PRICE_KEYS))
    printing = first(node, PRINTING_KEYS) or inherited_printing
    if d is not None and p is not None:
        yield (str(printing or "default"), d, p)
        return
    for key, value in node.items():
        next_printing = inherited_printing
        if isinstance(key, str) and looks_like_printing_label(key):
            next_printing = key
        yield from iter_price_rows(value, next_printing)


class TickermintPricesImporter(ApiImporter):
    """Fetches /products/{id}/prices for every matched product."""

    name = "tickermint_prices"
    api_base_url = API_BASE

    def api_probe_url(self) -> str:
        # Bare / returns 404. /products/search with a no-op query is the
        # cheapest documented endpoint and returns a small JSON envelope.
        return f"{API_BASE}/products/search?q=pikachu&game=pokemon"

    async def setup_schema(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(DDL)

    async def run(
        self,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        concurrency: int = 4,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        await self.setup_schema()

        own_session = session is None
        if own_session:
            session = aiohttp.ClientSession(
                headers={"User-Agent": "DVS/0.1"}
            )

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT DISTINCT m.product_id
                    FROM limitless_card_map m
                    WHERE m.match_status = 'matched'
                      AND m.product_id IS NOT NULL
                    ORDER BY m.product_id
                    """
                )
                product_ids = [r["product_id"] for r in rows]

            self.logger.info(
                "%d matched product_id(s) to fetch prices for.", len(product_ids)
            )
            if not product_ids:
                self.logger.info(
                    "Nothing to do. Run `dvs tickermint-products` first."
                )
                return

            sem = asyncio.Semaphore(concurrency)

            async def run(pid: int) -> None:
                async with sem:
                    await self._import_product(session, pid, from_date, to_date)

            await asyncio.gather(
                *(run(pid) for pid in product_ids), return_exceptions=True
            )
        finally:
            if own_session:
                await session.close()

    async def _import_product(
        self,
        session: aiohttp.ClientSession,
        product_id: int,
        from_date: date | None,
        to_date: date | None,
    ) -> None:
        payload = await self.get_json(
            session, f"{API_BASE}/products/{product_id}/prices"
        )
        rows = list(iter_price_rows(payload))
        if not rows:
            self.logger.warning(
                "product %d: no price rows parsed. "
                "Inspect the endpoint JSON before changing the parser.",
                product_id,
            )
            return

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                saved = 0
                for printing_type, price_date, market_price in rows:
                    if from_date and price_date < from_date:
                        continue
                    if to_date and price_date > to_date:
                        continue
                    await conn.execute(
                        """
                        INSERT INTO printing (product_id, printing_type)
                        VALUES ($1, $2) ON CONFLICT DO NOTHING
                        """,
                        product_id,
                        printing_type,
                    )
                    await conn.execute(
                        """
                        INSERT INTO daily_price (
                            product_id, printing_type, price_date, market_price
                        ) VALUES ($1, $2, $3, $4)
                        ON CONFLICT (product_id, printing_type, price_date)
                        DO UPDATE SET market_price = EXCLUDED.market_price
                        """,
                        product_id,
                        printing_type,
                        price_date,
                        market_price,
                    )
                    saved += 1

        self.logger.info("%d: saved %d daily price rows", product_id, saved)


__all__ = ["TickermintPricesImporter"]