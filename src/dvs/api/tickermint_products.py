"""TickerMint products importer (was 02_match_tickermint_products.py).

For every Limitless card in the ``card`` table, build a single search
query of the form ``"{card_name} {card_set_number}/{set_number}"`` --
where ``set_number`` is the TickerMint denominator resolved from the
Limitless ``set_code`` via the static map in :mod:`dvs.api.static` --
and POST it to ``/products/search``. The first candidate whose name
prefix-matches the queried card_name is treated as the match; one
upsert per card is written to ``card_product``.

Design notes:

* One HTTP request per card. We do NOT chase a follow-up detail call
  (/products/{id}); all fields we persist come from the search
  candidate.
* Idempotent: rerunning is safe. ``card_product.card_id`` is the PK.
  A later run that misses a previously matched card overwrites the row
  with a NULL product_id; a later run that hits a previously missed
  card overwrites the NULL row with the new product.
* Missing pieces (no card_number, or set_code with no denominator
  mapping) skip the HTTP call entirely and write a NULL row so the
  attempt is visible to later runs and to callers.
* The concrete request URL is logged at DEBUG so a postmortem on a
  surprised row can reproduce the exact search.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Iterable
from typing import Any

import aiohttp

from .base import ApiImporter
from .static import denominator_for

API_BASE = "https://api.tickermint.cards"

# ---------------------------------------------------------------------------
# Default schema (idempotent CREATE IF NOT EXISTS) and additive migrations.
# ---------------------------------------------------------------------------
# The DEFAULT_SCHEMA is the target shape. CREATE TABLE IF NOT EXISTS is a
# no-op against an existing table, so reruns are safe.
#
# The MIGRATIONS list is applied unconditionally on every setup_schema()
# call. Each entry is ADD ONLY: ALTER TABLE ... ADD COLUMN IF NOT EXISTS
# or CREATE [UNIQUE] INDEX IF NOT EXISTS. There are NO DROP / TRUNCATE /
# RENAME statements here -- rerunning setup_schema() never destroys
# existing rows.
#
# Why ADD COLUMN IF NOT EXISTS matters: an older run may have created
# card_product with the legacy shape (product_id BIGINT PRIMARY KEY,
# card_name TEXT NOT NULL, set_name, collector_number, rarity, image_url,
# source_url, group_id). The default CREATE IF NOT EXISTS is then a
# no-op, and the legacy table lacks card_id, search_query, set_number,
# card_set_number, fetched_at. The migrations add those columns as
# nullable (NULL is fine for both upserts and existing rows).
#
# The UNIQUE constraint on product_id is added as a UNIQUE INDEX IF
# NOT EXISTS, also non-destructive -- if duplicate product_ids already
# exist (possible in legacy data) the index simply fails to create and
# setup_schema() logs a warning instead of erroring out so the importer
# can still write the new columns.
DEFAULT_SCHEMA = """
CREATE TABLE IF NOT EXISTS card_product (
    card_id         BIGINT PRIMARY KEY REFERENCES card(card_id) ON DELETE CASCADE,
    product_id      BIGINT UNIQUE,
    group_id        BIGINT,
    card_name       TEXT,
    rarity          TEXT,
    search_query    TEXT,
    set_number      TEXT,
    card_set_number TEXT,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_card_product_product ON card_product (product_id);
CREATE INDEX IF NOT EXISTS ix_card_product_group   ON card_product (group_id);
CREATE INDEX IF NOT EXISTS ix_card_product_name    ON card_product (lower(card_name));
"""

# Each entry is one or more ADD-only statements separated by ';'. They
# run in order, every time. There is intentionally no DROP / TRUNCATE
# / RENAME here.
MIGRATIONS: tuple[str, ...] = (
    # Legacy card_product lacked these columns. Add as nullable so
    # existing rows stay valid.
    "ALTER TABLE card_product ADD COLUMN IF NOT EXISTS card_id         BIGINT",
    "ALTER TABLE card_product ADD COLUMN IF NOT EXISTS search_query    TEXT",
    "ALTER TABLE card_product ADD COLUMN IF NOT EXISTS set_number      TEXT",
    "ALTER TABLE card_product ADD COLUMN IF NOT EXISTS card_set_number TEXT",
    "ALTER TABLE card_product ADD COLUMN IF NOT EXISTS fetched_at      TIMESTAMPTZ",
    # UNIQUE INDEX rather than ALTER TABLE ADD CONSTRAINT so a legacy
    # database with duplicate product_ids can still upgrade columns
    # (the index just won't get built; we log a warning).
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_card_product_product_id ON card_product (product_id)",
    "CREATE INDEX        IF NOT EXISTS ix_card_product_group      ON card_product (group_id)",
    "CREATE INDEX        IF NOT EXISTS ix_card_product_name       ON card_product (lower(card_name))",
)

# ---------------------------------------------------------------------------
# Pure helpers (also exercised by tests/test_tickermint_matcher.py).
# ---------------------------------------------------------------------------

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _norm(value: Any) -> str:
    """Lowercase and strip everything that isn't alnum.

    Used to compare card names across spellings and punctuation --
    TickerMint embeds the card number in candidate names ("Pikachu
    ex - 199/165"), the Limitless side does not, so the only reliable
    equality check is on the alpha-numeric skeleton.
    """
    if value is None:
        return ""
    return _NON_ALNUM.sub("", str(value).lower())


def _to_results(payload: Any) -> list[dict]:
    """Coerce a TickerMint search payload to ``list[dict]``.

    Accepts the bare-list envelope (the documented shape), an
    envelope dict keyed by ``results`` / ``products`` / ``data`` /
    ``items``, or a single candidate dict that exposes a product
    identifier. Anything else yields an empty list.
    """
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("results", "products", "data", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        if _product_id(payload) is not None:
            return [payload]
    return []


def _product_id(candidate: dict) -> int | None:
    """Parse a TickerMint product id out of a candidate dict.

    Reads ``product_id`` / ``productId`` / ``id`` and casts to int.
    Returns ``None`` on any failure so the caller can treat missing
    and malformed ids uniformly.
    """
    for key in ("product_id", "productId", "id"):
        if key in candidate and candidate[key] not in (None, ""):
            try:
                return int(candidate[key])
            except (TypeError, ValueError):
                return None
    return None


def _candidate_name(candidate: dict) -> str:
    for key in ("name", "card_name", "product_name", "title"):
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _pick_match(candidates: list[dict], card_name: Any) -> dict | None:
    """Return the first candidate whose name shares the queried prefix.

    Blank query or empty candidate list → ``None``. "Prefix" is
    computed on the alnum-lowercased skeletons, so trailing text such
    as ``" - 199/165"`` doesn't break the match.
    """
    needle = _norm(card_name)
    if not needle:
        return None
    for candidate in candidates:
        if _norm(_candidate_name(candidate)).startswith(needle):
            return candidate
    return None


def build_search_query(
    card_name: Any,
    card_set_number: Any,
    set_number: Any,
) -> str | None:
    """Compose the literal ``/products/search`` query string.

    The template is ``"{card_name} {card_set_number}/{set_number}"``.
    Missing or empty pieces in any slot → ``None``; the caller skips
    the HTTP call entirely in that case.
    """
    parts = [card_name, card_set_number, set_number]
    if any(p is None or str(p).strip() == "" for p in parts):
        return None
    name, num, denom = (str(p).strip() for p in parts)
    return f"{name} {num}/{denom}"


# ---------------------------------------------------------------------------
# Importer.
# ---------------------------------------------------------------------------


class TickermintProductsImporter(ApiImporter):
    """Match every Limitless card to a TickerMint product.

    For each ``card`` row the importer:

    1. Builds a search query from ``card.card_name``,
       ``card.card_number`` (position within set) and the denominator
       resolved from ``card.set_code`` via :func:`denominator_for`.
    2. Logs the concrete URL at DEBUG, hits
       ``GET /products/search?q=<query>&game=pokemon`` once.
    3. Picks the first candidate whose name prefix-matches the
       queried card_name and upserts one row into ``card_product``.

    A miss (no candidates, no prefix-match, missing pieces) still
    writes a row so the attempt is visible to later runs.
    """

    name = "tickermint_products"
    api_base_url = API_BASE

    def api_probe_url(self) -> str:
        # Cheapest documented endpoint; we always have pokemon in the
        # default game so this returns a small JSON envelope quickly.
        return f"{API_BASE}/products/search?q=pikachu&game=pokemon"

    async def setup_schema(self) -> None:
        """Apply the default schema then run the additive migrations.

        Two phases, both idempotent and both non-destructive:

        1. ``DEFAULT_SCHEMA``: ``CREATE TABLE IF NOT EXISTS`` plus
           supporting ``CREATE INDEX IF NOT EXISTS`` -- establishes the
           target shape on a fresh database.
        2. ``MIGRATIONS``: a fixed sequence of ``ALTER TABLE ...
           ADD COLUMN IF NOT EXISTS`` and ``CREATE [UNIQUE] INDEX IF
           NOT EXISTS`` -- backfills columns a legacy ``card_product``
           might be missing without touching existing rows.

        Every statement uses ``IF NOT EXISTS`` so calling
        ``setup_schema()`` repeatedly is safe. There are no
        ``DROP``/``TRUNCATE``/``RENAME`` calls in this module -- if
        you need to drop a table, do it manually via ``psql``.
        """
        async with self.pool.acquire() as conn:
            await conn.execute(DEFAULT_SCHEMA)
            for stmt in MIGRATIONS:
                try:
                    await conn.execute(stmt)
                except Exception as exc:  # noqa: BLE001
                    # Legacy data may prevent creating the unique index
                    # (e.g. duplicate product_ids in old rows). Log and
                    # continue -- the importer can still write new rows
                    # even if the optional unique index never appears.
                    self.logger.warning(
                        "card_product migration skipped: %s (stmt: %s)",
                        exc,
                        stmt,
                    )

    async def run(
        self,
        *,
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
            cards = [dict(r) for r in rows]

            self.logger.info(
                "%d card(s) to resolve against TickerMint.", len(cards)
            )
            if not cards:
                self.logger.info("Nothing to do. Run `dvs limitless` first.")
                return

            total = len(cards)
            done = 0
            in_flight = 0
            failed = 0
            matched = 0
            missed = 0
            skipped = 0
            started_at = time.monotonic()
            progress_lock = asyncio.Lock()

            sem = asyncio.Semaphore(concurrency)

            async def run_card(card: dict) -> tuple[str, int | None]:
                nonlocal done, in_flight, failed, matched, missed, skipped
                async with sem:
                    async with progress_lock:
                        in_flight += 1
                        self.logger.debug(
                            f"starting {card['card_id']} {card['card_name']} {card['set_code']}/{card['card_number']}"
                        )
                    try:
                        outcome, pid = await self._import_card(session, card)
                    except BaseException as exc:
                        async with progress_lock:
                            in_flight -= 1
                            done += 1
                            failed += 1
                        self.logger.error(
                            f"{card['card_id']} {card['card_name']} {card['set_code']}/{card['card_number']} import failed: {exc}"
                        )
                        return ("failed", None)

                    async with progress_lock:
                        in_flight -= 1
                        done += 1
                        if outcome == "matched":
                            matched += 1
                        elif outcome == "missed":
                            missed += 1
                        else:
                            skipped += 1
                        elapsed = time.monotonic() - started_at
                        if done % 50 == 0 or done == total:
                            self.logger.info(
                                "progress: %d/%d done, %d in flight, "
                                "matched=%d missed=%d skipped=%d failed=%d, "
                                "%.0fs elapsed",
                                done,
                                total,
                                in_flight,
                                matched,
                                missed,
                                skipped,
                                failed,
                                elapsed,
                            )
                    return (outcome, pid)

            results = await asyncio.gather(
                *(run_card(card) for card in cards), return_exceptions=False
            )

            self.logger.info(
                "Done. %d card(s) processed: %d matched, %d missed, "
                "%d skipped, %d failed in %.0fs.",
                total,
                sum(1 for o, _ in results if o == "matched"),
                sum(1 for o, _ in results if o == "missed"),
                sum(1 for o, _ in results if o == "skipped"),
                sum(1 for o, _ in results if o == "failed"),
                time.monotonic() - started_at,
            )
        finally:
            if own_session:
                await session.close()

    # ------------------------------------------------------------------
    # Per-card worker.
    # ------------------------------------------------------------------

    async def _import_card(
        self,
        session: aiohttp.ClientSession,
        card: dict,
    ) -> tuple[str, int | None]:
        """Resolve one card. Returns ``(outcome, product_id)``.

        outcome ∈ {"matched", "missed", "skipped"}. ``product_id`` is
        ``None`` unless outcome == "matched".
        """
        card_id = card["card_id"]
        card_name = card.get("card_name") or ""
        set_code = card.get("set_code")
        card_set_number = card.get("card_number")

        # Resolve TickerMint denominator from the Limitless set code.
        # Missing mapping -> we can't query narrowly, so skip.
        set_number = denominator_for(set_code)

        query = build_search_query(card_name, card_set_number, set_number)
        if query is None:
            self.logger.debug(
                "card_id=%s: skipping (card_name=%r set_code=%r "
                "card_number=%r denom=%r)",
                card_id,
                card_name,
                set_code,
                card_set_number,
                set_number,
            )
            await self._upsert(
                card_id,
                product_id=None,
                group_id=None,
                card_name=None,
                rarity=None,
                search_query=None,
                set_number=str(set_number) if set_number else None,
                card_set_number=str(card_set_number)
                if card_set_number not in (None, "")
                else None,
            )
            return ("skipped", None)

        url = f"{API_BASE}/products/search"
        params = {"q": query, "game": "pokemon"}

        # DEBUG: the user explicitly asked for the concrete requested URL
        # so we can reproduce a surprising row later.
        self.logger.debug(
            "card_id=%s: GET %s params=%s", card_id, url, params
        )

        payload = await self.get_json(session, url, params=params)
        candidates = _to_results(payload)
        chosen = _pick_match(candidates, card_name)

        if chosen is None:
            self.logger.info(
                "card_id=%s: no TickerMint match for query=%r "
                "(%d candidate(s) from API)",
                card_id,
                query,
                len(candidates),
            )
            await self._upsert(
                card_id,
                product_id=None,
                group_id=None,
                card_name=None,
                rarity=None,
                search_query=query,
                set_number=set_number,
                card_set_number=card_set_number,
            )
            return ("missed", None)

        pid = _product_id(chosen)
        if pid is None:
            self.logger.info(
                "card_id=%s: candidate for query=%r had no product_id; "
                "treating as miss",
                card_id,
                query,
            )
            await self._upsert(
                card_id,
                product_id=None,
                group_id=None,
                card_name=None,
                rarity=None,
                search_query=query,
                set_number=set_number,
                card_set_number=card_set_number,
            )
            return ("missed", None)

        group_id = _maybe_int(chosen.get("group_id"))
        card_name_from_api = _candidate_name(chosen) or None
        rarity = chosen.get("rarity") or None
        if rarity is not None:
            rarity = str(rarity)

        await self._upsert(
            card_id,
            product_id=pid,
            group_id=group_id,
            card_name=card_name_from_api,
            rarity=rarity,
            search_query=query,
            set_number=set_number,
            card_set_number=card_set_number,
        )
        self.logger.debug(
            "card_id=%s: matched -> product_id=%s query=%r",
            card_id,
            pid,
            query,
        )
        return ("matched", pid)

    async def _upsert(
        self,
        card_id: int,
        *,
        product_id: int | None,
        group_id: int | None,
        card_name: str | None,
        rarity: str | None,
        search_query: str | None,
        set_number: str | None,
        card_set_number: str | None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO card_product (
                    card_id, product_id, group_id, card_name, rarity,
                    search_query, set_number, card_set_number
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (card_id) DO UPDATE
                SET product_id = EXCLUDED.product_id,
                    group_id = EXCLUDED.group_id,
                    card_name = EXCLUDED.card_name,
                    rarity = EXCLUDED.rarity,
                    search_query = EXCLUDED.search_query,
                    set_number = EXCLUDED.set_number,
                    card_set_number = EXCLUDED.card_set_number,
                    fetched_at = now()
                """,
                card_id,
                product_id,
                group_id,
                card_name,
                rarity,
                search_query,
                set_number,
                card_set_number,
            )


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "TickermintProductsImporter",
    "build_search_query",
]


# Silence "imported but unused" linters for helpers re-exported for tests.
_ = (
    Iterable,
    _norm,
    _to_results,
    _product_id,
    _candidate_name,
    _pick_match,
    _maybe_int,
)
