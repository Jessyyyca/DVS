"""Match Limitless cards to TickerMint products (was 02_...)."""

from __future__ import annotations

import asyncio
import re
from typing import Any

import aiohttp

from .base import ApiImporter

API_BASE = "https://api.tickermint.cards"

DDL = """
CREATE TABLE IF NOT EXISTS card_product (
    product_id BIGINT PRIMARY KEY,
    card_name TEXT NOT NULL,
    set_name TEXT NULL,
    collector_number TEXT NULL,
    rarity TEXT NULL,
    image_url TEXT NULL,
    source_url TEXT NULL,
    group_id BIGINT NULL
);

-- 1:N: one Limitless card identity can map to many TickerMint products.
-- The matcher wipes existing rows for a card_id before re-inserting.
CREATE TABLE IF NOT EXISTS limitless_card_map (
    limitless_card_id BIGINT NOT NULL REFERENCES card(card_id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL REFERENCES card_product(product_id) ON DELETE CASCADE,
    match_kind TEXT NOT NULL CHECK (
        match_kind IN ('exact_number', 'exact_name')
    ),
    search_query TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (limitless_card_id, product_id)
);
"""


def norm(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def pick(obj: dict, *keys: str) -> Any:
    for key in keys:
        if key in obj and obj[key] not in (None, ""):
            return obj[key]
    return None


def to_results(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("results", "products", "data", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        if pick(payload, "product_id", "productId", "id") is not None:
            return [payload]
    return []


def get_product_id(candidate: dict) -> int | None:
    value = pick(candidate, "product_id", "productId", "id")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def candidate_name(c: dict) -> str:
    return str(pick(c, "name", "card_name", "product_name", "title") or "")


def candidate_number(c: dict) -> str:
    return str(
        pick(
            c,
            "number",
            "collector_number",
            "collectorNumber",
            "card_number",
        )
        or ""
    )


def filter_candidates(
    candidates: list[dict],
    card_name: str,
    card_number: str | None,
) -> list[tuple[dict, str]]:
    """Return every name-matching product tagged with how well it fits.

    match_kind is 'exact_number' when name and collector number both line
    up, and 'exact_name' when only the name does. Returns [] when no
    candidate shares the card's name (the Limitless card is unmatched).
    """
    name_matches = [
        c for c in candidates if norm(candidate_name(c)) == norm(card_name)
    ]
    if not name_matches:
        return []
    if card_number:
        with_number = [
            c
            for c in name_matches
            if norm(candidate_number(c)) == norm(card_number)
        ]
        if with_number:
            return [(c, "exact_number") for c in with_number]
    return [(c, "exact_name") for c in name_matches]


def set_fields(detail: dict) -> tuple[str | None, int | None]:
    raw_set = pick(detail, "set", "set_info", "group")
    if isinstance(raw_set, dict):
        set_name = pick(raw_set, "name", "set_name", "title")
        group_id = pick(raw_set, "group_id", "groupId", "id")
    else:
        set_name = raw_set
        group_id = pick(detail, "group_id", "groupId")
    try:
        group_id = int(group_id) if group_id is not None else None
    except (TypeError, ValueError):
        group_id = None
    return (
        str(set_name) if set_name not in (None, "") else None,
        group_id,
    )


class TickermintProductsImporter(ApiImporter):
    """Searches TickerMint for each Limitless card and saves product identity."""

    name = "tickermint_products"
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
        rematch: bool = False,
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
                    SELECT card_id, card_name, set_code, card_number
                    FROM card
                    ORDER BY card_id
                    """
                )
                cards = [
                    (r["card_id"], r["card_name"], r["set_code"], r["card_number"])
                    for r in rows
                ]

            self.logger.info(
                "%d card row(s) to consider (rematch=%s).", len(cards), rematch
            )
            if not cards:
                self.logger.info(
                    "Nothing to do. Populate the card table first "
                    "(e.g. dvs limitless --from-date ...)."
                )
                return

            sem = asyncio.Semaphore(concurrency)

            async def run(card: tuple) -> None:
                async with sem:
                    await self._match_card(session, card, rematch)

            await asyncio.gather(
                *(run(c) for c in cards), return_exceptions=True
            )
        finally:
            if own_session:
                await session.close()

    async def _match_card(
        self,
        session: aiohttp.ClientSession,
        card: tuple,
        rematch: bool,
    ) -> None:
        card_id, card_name, set_code, card_number = card

        async with self.pool.acquire() as conn:
            if not rematch:
                existing = await conn.fetchval(
                    "SELECT 1 FROM limitless_card_map WHERE limitless_card_id = $1",
                    card_id,
                )
                if existing:
                    return

            parts = [card_name]
            if set_code:
                parts.append(set_code)
            if card_number:
                parts.append(card_number)
            query = " ".join(parts)

            payload = await self.get_json(
                session,
                f"{API_BASE}/products/search",
                params={"q": query, "game": "pokemon"},
            )
            candidates = to_results(payload)
            pairs = filter_candidates(candidates, card_name, card_number)

            kinds: list[str] = []
            async with conn.transaction():
                # Wipe this card's mapping rows first so the table stays
                # in lockstep with what TickerMint just returned -- stale
                # candidates from a previous run do not linger.
                await conn.execute(
                    "DELETE FROM limitless_card_map WHERE limitless_card_id = $1",
                    card_id,
                )
                for candidate, kind in pairs:
                    pid = get_product_id(candidate)
                    if pid is None:
                        continue
                    detail = await self.get_json(
                        session, f"{API_BASE}/products/{pid}"
                    )
                    product_id = await self._save_product(conn, detail, pid)
                    await conn.execute(
                        """
                        INSERT INTO limitless_card_map (
                            limitless_card_id, product_id,
                            match_kind, search_query, captured_at
                        ) VALUES ($1, $2, $3, $4, now())
                        ON CONFLICT (limitless_card_id, product_id) DO NOTHING
                        """,
                        card_id,
                        product_id,
                        kind,
                        query,
                    )
                    kinds.append(kind)

        if not kinds:
            self.logger.info(
                "%d: %s %s %s -> unmatched",
                card_id,
                card_name,
                set_code or "",
                card_number or "",
            )
            return

        tally: dict[str, int] = {}
        for kind in kinds:
            tally[kind] = tally.get(kind, 0) + 1
        summary = ", ".join(f"{n} {k}" for k, n in tally.items())
        self.logger.info(
            "%d: %s %s %s -> %d candidate(s) [%s]",
            card_id,
            card_name,
            set_code or "",
            card_number or "",
            len(kinds),
            summary,
        )

    async def _save_product(self, conn, detail: dict, fallback_product_id: int) -> int:
        product_id = get_product_id(detail) or fallback_product_id
        set_name, group_id = set_fields(detail)
        card_name = str(
            pick(detail, "name", "card_name", "product_name", "title")
            or product_id
        )
        collector_number = pick(
            detail,
            "number",
            "collector_number",
            "collectorNumber",
            "card_number",
        )
        rarity = pick(detail, "rarity")
        image_url = pick(detail, "image", "image_url", "imageUrl")
        source_url = pick(
            detail,
            "url",
            "source_url",
            "sourceUrl",
            "page_url",
            "pageUrl",
        )

        await conn.execute(
            """
            INSERT INTO card_product (
                product_id, card_name, set_name, collector_number,
                rarity, image_url, source_url, group_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (product_id) DO UPDATE
            SET card_name = EXCLUDED.card_name,
                set_name = EXCLUDED.set_name,
                collector_number = EXCLUDED.collector_number,
                rarity = EXCLUDED.rarity,
                image_url = EXCLUDED.image_url,
                source_url = EXCLUDED.source_url,
                group_id = EXCLUDED.group_id
            """,
            product_id,
            card_name,
            set_name,
            str(collector_number) if collector_number is not None else None,
            str(rarity) if rarity is not None else None,
            str(image_url) if image_url is not None else None,
            str(source_url) if source_url is not None else None,
            group_id,
        )
        return product_id


__all__ = ["TickermintProductsImporter"]