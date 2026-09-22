#!/usr/bin/env python3
"""
01_import_limitless.py

Imports only the Limitless data needed to calculate competitive card usage:
  DECK(deck_id, source_event_id, event_date, format)
  CARD(card_id, card_name, set_code, card_number)
  DECK_CARD(deck_id, card_id, quantity)

No player, organizer, match, standing, or tournament table is persisted.

Requirements:
    pip install requests "psycopg[binary]"

Example:
    export LIMITLESS_DB_DSN="postgresql://postgres:postgres@localhost:5432/limitless_source"
    python 01_import_limitless.py --from-date 2026-01-01 --format STANDARD
"""

import argparse
import os
import time
import uuid
from datetime import date, datetime
from typing import Any, Iterable

import psycopg
import requests

API_BASE = "https://play.limitlesstcg.com/api"
DEFAULT_PAGE_SIZE = 50


DDL = """
CREATE TABLE IF NOT EXISTS deck (
    deck_id UUID PRIMARY KEY,
    source_event_id TEXT NOT NULL,
    event_date DATE NOT NULL,
    format TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_deck_date_format
    ON deck (event_date, format);

CREATE TABLE IF NOT EXISTS card (
    card_id BIGSERIAL PRIMARY KEY,
    card_name TEXT NOT NULL,
    set_code TEXT NULL,
    card_number TEXT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_card_identity
    ON card (
        lower(card_name),
        COALESCE(set_code, ''),
        COALESCE(card_number, '')
    );

CREATE TABLE IF NOT EXISTS deck_card (
    deck_id UUID NOT NULL REFERENCES deck(deck_id) ON DELETE CASCADE,
    card_id BIGINT NOT NULL REFERENCES card(card_id),
    quantity SMALLINT NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (deck_id, card_id)
);
"""


def api_get(session: requests.Session, url: str, params: dict | None = None) -> Any:
    """GET with simple handling for Limitless rate limits/transient errors."""
    for attempt in range(6):
        r = session.get(url, params=params, timeout=45)

        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", "5"))
            time.sleep(retry_after)
            continue

        if 500 <= r.status_code < 600:
            time.sleep(2 ** attempt)
            continue

        r.raise_for_status()
        return r.json()

    raise RuntimeError(f"Request failed repeatedly: {url}")


def parse_date(value: str) -> date:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def iter_card_records(node: Any) -> Iterable[dict]:
    """
    Extract card-like objects from Limitless' game-specific decklist payload.

    The developer docs intentionally describe decklist as game-specific, so
    this parser does not assume a single top-level layout. It accepts nested
    objects/lists containing fields such as:
      name, set, number, count
    """
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
            "set": str(node["set"]).strip() if node.get("set") not in (None, "") else None,
            "number": str(node["number"]).strip() if node.get("number") not in (None, "") else None,
            "quantity": quantity,
        }
        return

    for value in node.values():
        yield from iter_card_records(value)


def get_or_create_card(cur: psycopg.Cursor, card: dict) -> int:
    cur.execute(
        """
        SELECT card_id
        FROM card
        WHERE lower(card_name) = lower(%s)
          AND COALESCE(set_code, '') = COALESCE(%s, '')
          AND COALESCE(card_number, '') = COALESCE(%s, '')
        """,
        (card["name"], card["set"], card["number"]),
    )
    row = cur.fetchone()
    if row:
        return row[0]

    cur.execute(
        """
        INSERT INTO card (card_name, set_code, card_number)
        VALUES (%s, %s, %s)
        RETURNING card_id
        """,
        (card["name"], card["set"], card["number"]),
    )
    return cur.fetchone()[0]


def make_deck_id(tournament_id: str, source_player_id: str) -> uuid.UUID:
    # Player ID is used only transiently to make the deck ID stable on reruns.
    # It is NOT persisted in the source database.
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"https://play.limitlesstcg.com/{tournament_id}/{source_player_id}",
    )


def import_tournament(
    conn: psycopg.Connection,
    session: requests.Session,
    tournament: dict,
) -> tuple[int, int]:
    tournament_id = tournament["id"]
    event_date = parse_date(tournament["date"])
    fmt = tournament.get("format") or "UNKNOWN"

    standings = api_get(
        session,
        f"{API_BASE}/tournaments/{tournament_id}/standings",
    )

    imported_decks = 0
    imported_rows = 0

    with conn.cursor() as cur:
        for ordinal, standing in enumerate(standings):
            decklist = standing.get("decklist")
            if not decklist:
                continue

            source_player_id = str(standing.get("player") or f"row-{ordinal}")
            deck_id = make_deck_id(tournament_id, source_player_id)

            cur.execute(
                """
                INSERT INTO deck (deck_id, source_event_id, event_date, format)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (deck_id) DO UPDATE
                SET source_event_id = EXCLUDED.source_event_id,
                    event_date = EXCLUDED.event_date,
                    format = EXCLUDED.format
                """,
                (deck_id, tournament_id, event_date, fmt),
            )

            # Makes reruns idempotent if a published decklist changes.
            cur.execute("DELETE FROM deck_card WHERE deck_id = %s", (deck_id,))

            cards = list(iter_card_records(decklist))
            if not cards:
                print(
                    f"WARNING: no card rows parsed for tournament {tournament_id}, "
                    f"deck {deck_id}. Inspect that decklist payload."
                )
                continue

            # Merge duplicate exact card references inside one deck.
            merged: dict[tuple, int] = {}
            for card in cards:
                key = (card["name"], card["set"], card["number"])
                merged[key] = merged.get(key, 0) + card["quantity"]

            for (name, set_code, number), quantity in merged.items():
                card_id = get_or_create_card(
                    cur,
                    {
                        "name": name,
                        "set": set_code,
                        "number": number,
                    },
                )

                cur.execute(
                    """
                    INSERT INTO deck_card (deck_id, card_id, quantity)
                    VALUES (%s, %s, %s)
                    """,
                    (deck_id, card_id, quantity),
                )
                imported_rows += 1

            imported_decks += 1

    conn.commit()
    return imported_decks, imported_rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", required=True, type=date.fromisoformat)
    parser.add_argument("--to-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--format", default="STANDARD")
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--sleep", type=float, default=0.20)
    args = parser.parse_args()

    dsn = os.environ.get("LIMITLESS_DB_DSN")
    if not dsn:
        raise SystemExit("Set LIMITLESS_DB_DSN.")

    session = requests.Session()
    session.headers["User-Agent"] = "PokemonDWH-UniversityProject/1.0"

    total_decks = 0
    total_deck_cards = 0

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()

        stop = False
        for page in range(1, args.max_pages + 1):
            tournaments = api_get(
                session,
                f"{API_BASE}/tournaments",
                params={
                    "game": "PTCG",
                    "format": args.format,
                    "limit": DEFAULT_PAGE_SIZE,
                    "page": page,
                },
            )

            if not tournaments:
                break

            for tournament in tournaments:
                event_date = parse_date(tournament["date"])

                if event_date > args.to_date:
                    continue

                if event_date < args.from_date:
                    stop = True
                    continue

                decks, rows = import_tournament(conn, session, tournament)
                total_decks += decks
                total_deck_cards += rows
                print(
                    f"{event_date} {tournament['id']}: "
                    f"{decks} decks, {rows} deck-card rows"
                )
                time.sleep(args.sleep)

            if stop:
                # /tournaments returns recent tournaments first.
                break

    print(f"Done. Imported {total_decks} decks and {total_deck_cards} deck-card rows.")


if __name__ == "__main__":
    main()
