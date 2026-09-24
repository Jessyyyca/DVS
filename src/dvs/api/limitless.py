"""Limitless tournament-decklist importer (was 01_import_limitless.py)."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

import aiohttp
import asyncpg

from .base import ApiImporter

API_BASE = "https://play.limitlesstcg.com/api"
DEFAULT_PAGE_SIZE = 50

DDL = """
CREATE TABLE IF NOT EXISTS deck (
    deck_id UUID PRIMARY KEY,
    source_event_id TEXT NOT NULL,
    event_date DATE NOT NULL,
    format TEXT NOT NULL,
    player_id TEXT,
    wins INT,
    losses INT,
    ties INT,
    placings INT,
    deck_archtype_id TEXT,
    deck_archtype_name TEXT,
    play_date DATE
);

-- Migration safety: the legacy deck table predates several of the columns
-- above. ADD COLUMN IF NOT EXISTS is a no-op on a fresh install and fills
-- the gap when the table was created by an older importer run.
ALTER TABLE deck ADD COLUMN IF NOT EXISTS player_id          TEXT;
ALTER TABLE deck ADD COLUMN IF NOT EXISTS wins               INT;
ALTER TABLE deck ADD COLUMN IF NOT EXISTS losses             INT;
ALTER TABLE deck ADD COLUMN IF NOT EXISTS ties               INT;
ALTER TABLE deck ADD COLUMN IF NOT EXISTS placings           INT;
ALTER TABLE deck ADD COLUMN IF NOT EXISTS deck_archtype_id   TEXT;
ALTER TABLE deck ADD COLUMN IF NOT EXISTS deck_archtype_name TEXT;
ALTER TABLE deck ADD COLUMN IF NOT EXISTS play_date          DATE;

CREATE INDEX IF NOT EXISTS ix_deck_date_format ON deck (event_date, format);
CREATE INDEX IF NOT EXISTS ix_deck_player      ON deck (player_id);
CREATE INDEX IF NOT EXISTS ix_deck_archtype    ON deck (deck_archtype_id);

CREATE TABLE IF NOT EXISTS card (
    card_id BIGSERIAL PRIMARY KEY,
    card_name TEXT NOT NULL,
    set_code TEXT NULL,
    card_number TEXT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_card_identity
    ON card (lower(card_name), COALESCE(set_code, ''), COALESCE(card_number, ''));

CREATE TABLE IF NOT EXISTS deck_card (
    deck_id UUID NOT NULL REFERENCES deck(deck_id) ON DELETE CASCADE,
    card_id BIGINT NOT NULL REFERENCES card(card_id),
    quantity SMALLINT NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (deck_id, card_id)
);
"""


def parse_date(value: str) -> date:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def iter_card_records(node: Any) -> Iterable[dict]:
    """Walk nested decklist payloads to find card-like objects."""
    if isinstance(node, list):
        for item in node:
            yield from iter_card_records(item)
        return
    if not isinstance(node, dict):
        return
    has_name = isinstance(node.get("name"), str) and node["name"].strip()
    looks_like_card = has_name and any(
        key in node for key in ("count", "quantity", "set", "number")
    )
    if looks_like_card:
        quantity = node.get("count", node.get("quantity", 1))
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            quantity = 1
        yield {
            "name": node["name"].strip(),
            "set": str(node["set"]).strip()
            if node.get("set") not in (None, "")
            else None,
            "number": str(node["number"]).strip()
            if node.get("number") not in (None, "")
            else None,
            "quantity": quantity,
        }
        return
    for value in node.values():
        yield from iter_card_records(value)


def make_deck_id(tournament_id: str, source_player_id: str) -> uuid.UUID:
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"https://play.limitlesstcg.com/{tournament_id}/{source_player_id}",
    )


class LimitlessImporter(ApiImporter):
    """Imports Limitless tournaments into deck / card / deck_card."""

    name = "limitless"
    api_base_url = API_BASE

    def api_probe_url(self) -> str:
        # Bare /api returns 404. /tournaments is the cheapest documented
        # endpoint and always returns 200 with an empty list when no args.
        return f"{API_BASE}/tournaments?limit=1"

    async def setup_schema(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(DDL)

    async def run(
        self,
        *,
        from_date: date,
        to_date: date,
        format: str = "STANDARD",
        max_pages: int = 10000,
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
            self.logger.debug(f'collecting tournaments from {from_date} to {to_date}')
            tournaments = await self._collect_tournaments(
                session, format, from_date, to_date, max_pages
            )

            self.logger.info(
                "%d tournament(s) in [%s..%s] format=%s",
                len(tournaments),
                from_date,
                to_date,
                format,
            )
            if not tournaments:
                self.logger.info("Nothing to do in that date range.")
                return

            total = len(tournaments)
            done = 0
            in_flight = 0
            total_decks = 0
            total_rows = 0
            failed = 0
            progress_lock = asyncio.Lock()
            started_at = time.monotonic()

            sem = asyncio.Semaphore(concurrency)

            async def run(t: dict) -> tuple[int, int]:
                nonlocal done, in_flight, total_decks, total_rows, failed
                async with sem:
                    async with progress_lock:
                        in_flight += 1
                        self.logger.info(
                            "starting tournament id=%s date=%s "
                            "(%d in flight, %d/%d done)",
                            t.get("id"),
                            t.get("date"),
                            in_flight,
                            done,
                            total,
                        )
                    try:
                        return await self._import_tournament(session, t)
                    finally:
                        async with progress_lock:
                            in_flight -= 1
                            done += 1
                            elapsed = time.monotonic() - started_at
                            self.logger.info(
                                "progress: %d/%d done, %d in flight, "
                                "%d failed, %.0fs elapsed",
                                done,
                                total,
                                in_flight,
                                failed,
                                elapsed,
                            )

            results = await asyncio.gather(
                *(run(t) for t in tournaments), return_exceptions=True
            )

            for r in results:
                if isinstance(r, BaseException):
                    self.logger.error("tournament import failed: %r", r)
                    failed += 1
                    continue
                d, c = r
                total_decks += d
                total_rows += c

            self.logger.info(
                "Done. Imported %d decks and %d deck-card rows in %d tournament(s) "
                "(%d failed) in %.0fs.",
                total_decks,
                total_rows,
                total,
                failed,
                time.monotonic() - started_at,
            )
        finally:
            if own_session:
                await session.close()

    async def _collect_tournaments(
        self,
        session: aiohttp.ClientSession,
        fmt: str,
        from_date: date,
        to_date: date,
        max_pages: int,
    ) -> list[dict]:
        out: list[dict] = []
        for page in range(1, max_pages + 1):
            self.logger.info("fetching tournaments page %d/%d", page, max_pages)
            tournaments = await self.get_json(
                session,
                f"{API_BASE}/tournaments",
                params={
                    "game": "PTCG",
                    "format": fmt,
                    "limit": DEFAULT_PAGE_SIZE,
                    "page": page,
                },
            )
            if not tournaments:
                self.logger.info("page %d empty, stopping pagination", page)
                break
            stop = False
            kept = 0
            for t in tournaments:
                event_date = parse_date(t["date"])
                if event_date > to_date:
                    continue
                if event_date < from_date:
                    stop = True
                    continue
                out.append(t)
                kept += 1
            self.logger.info(
                "page %d returned %d tournaments, %d in date range",
                page,
                len(tournaments),
                kept,
            )
            if stop:
                self.logger.info(
                    "reached from_date %s, stopping pagination", from_date
                )
                break
        return out

    async def _import_tournament(
        self, session: aiohttp.ClientSession, tournament: dict
    ) -> tuple[int, int]:
        tournament_id = tournament["id"]
        event_date = parse_date(tournament["date"])
        fmt = tournament.get("format") or "UNKNOWN"

        self.logger.info(
            "  fetching standings for %s (%s)", tournament_id, event_date
        )
        standings = await self.get_json(
            session, f"{API_BASE}/tournaments/{tournament_id}/standings"
        )
        self.logger.info(
            "  %s: %d standings, persisting",
            tournament_id,
            len(standings) if isinstance(standings, list) else "?",
        )

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                decks, rows = await self._persist_tournament(
                    conn, tournament_id, event_date, fmt, standings
                )

        self.logger.info(
            "%s %s: %d decks, %d deck-card rows",
            event_date,
            tournament_id,
            decks,
            rows,
        )
        return decks, rows

    async def _persist_tournament(
        self,
        conn,
        tournament_id: str,
        event_date: date,
        fmt: str,
        standings: list[dict],
    ) -> tuple[int, int]:
        imported_decks = 0
        imported_rows = 0

        for ordinal, standing in enumerate(standings):
            decklist = standing.get("decklist")
            if not decklist:
                continue

            source_player_id = str(
                standing.get("player") or f"row-{ordinal}"
            )
            deck_id = make_deck_id(tournament_id, source_player_id)

            record = standing.get("record") or {}
            wins = _maybe_int(record.get("wins"))
            losses = _maybe_int(record.get("losses"))
            ties = _maybe_int(record.get("ties"))
            placings = _maybe_int(
                standing.get("placing")
                or standing.get("placement")
                or standing.get("rank")
                or standing.get("position")
            )
            archetype = standing.get("deck_archtype") or standing.get("deck") or {}
            archtype_id = (
                str(archetype.get("id"))
                if isinstance(archetype, dict) and archetype.get("id") is not None
                else None
            )
            archtype_name = (
                archetype.get("name")
                if isinstance(archetype, dict)
                else (archetype if isinstance(archetype, str) else None)
            )

            self.logger.debug(
                "deck %s player=%s record=%d-%d-%d placing=%s archetype=%s",
                deck_id,
                source_player_id,
                wins or 0,
                losses or 0,
                ties or 0,
                placings,
                archtype_name,
            )

            await conn.execute(
                """
                INSERT INTO deck (
                    deck_id, source_event_id, event_date, format,
                    player_id, wins, losses, ties, placings,
                    deck_archtype_id, deck_archtype_name, play_date
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
                )
                ON CONFLICT (deck_id) DO UPDATE
                SET source_event_id = EXCLUDED.source_event_id,
                    event_date = EXCLUDED.event_date,
                    format = EXCLUDED.format,
                    player_id = EXCLUDED.player_id,
                    wins = EXCLUDED.wins,
                    losses = EXCLUDED.losses,
                    ties = EXCLUDED.ties,
                    placings = EXCLUDED.placings,
                    deck_archtype_id = EXCLUDED.deck_archtype_id,
                    deck_archtype_name = EXCLUDED.deck_archtype_name,
                    play_date = EXCLUDED.play_date
                """,
                deck_id,
                tournament_id,
                event_date,
                fmt,
                source_player_id,
                wins,
                losses,
                ties,
                placings,
                archtype_id,
                archtype_name,
                event_date,
            )
            await conn.execute(
                "DELETE FROM deck_card WHERE deck_id = $1", deck_id
            )

            cards = list(iter_card_records(decklist))
            if not cards:
                self.logger.warning(
                    "no card rows parsed for tournament %s, deck %s",
                    tournament_id,
                    deck_id,
                )
                continue

            merged: dict[tuple, int] = {}
            for card in cards:
                key = (card["name"], card["set"], card["number"])
                merged[key] = merged.get(key, 0) + card["quantity"]

            for (name, set_code, number), quantity in merged.items():
                card_id = await self._get_or_create_card(
                    conn, name, set_code, number
                )
                await conn.execute(
                    """
                    INSERT INTO deck_card (deck_id, card_id, quantity)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (deck_id, card_id) DO NOTHING
                    """,
                    deck_id,
                    card_id,
                    quantity,
                )
                imported_rows += 1

            imported_decks += 1

        return imported_decks, imported_rows

    async def _get_or_create_card(
        self, conn, name: str, set_code: str | None, number: str | None
    ) -> int:
        row = await conn.fetchrow(
            """
            SELECT card_id FROM card
            WHERE lower(card_name) = lower($1)
              AND COALESCE(set_code, '') = COALESCE($2, '')
              AND COALESCE(card_number, '') = COALESCE($3, '')
            """,
            name,
            set_code,
            number,
        )
        if row:
            return row["card_id"]
        # Race-safe fallback: a concurrent rerun may have inserted the same
        # card identity between our SELECT and this INSERT. Treat the duplicate
        # as the winner of the race.
        try:
            return await conn.fetchval(
                """
                INSERT INTO card (card_name, set_code, card_number)
                VALUES ($1, $2, $3)
                RETURNING card_id
                """,
                name,
                set_code,
                number,
            )
        except asyncpg.UniqueViolationError:
            row = await conn.fetchrow(
                """
                SELECT card_id FROM card
                WHERE lower(card_name) = lower($1)
                  AND COALESCE(set_code, '') = COALESCE($2, '')
                  AND COALESCE(card_number, '') = COALESCE($3, '')
                """,
                name,
                set_code,
                number,
            )
            return row["card_id"]


__all__ = ["LimitlessImporter"]