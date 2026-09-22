#!/usr/bin/env python3
"""
02_match_tickermint_products.py

Reads CARD rows from the Limitless source DB and matches them to TickerMint
products. Stores only TickerMint product identity needed for later price loads.

This intentionally does NOT import TickerMint prices; that is script 03.

Requirements:
    pip install requests "psycopg[binary]"

Example:
    export LIMITLESS_DB_DSN="postgresql://postgres:postgres@localhost:5432/limitless_source"
    export TICKERMINT_DB_DSN="postgresql://postgres:postgres@localhost:5432/tickermint_source"
    python 02_match_tickermint_products.py
"""

import argparse
import os
import re
import time
from typing import Any

import psycopg
import requests

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

CREATE TABLE IF NOT EXISTS limitless_card_map (
    limitless_card_id BIGINT PRIMARY KEY,
    product_id BIGINT NULL REFERENCES card_product(product_id),
    match_status TEXT NOT NULL CHECK (
        match_status IN ('matched', 'unmatched', 'ambiguous')
    ),
    search_query TEXT NOT NULL,
    matched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    note TEXT NULL
);
"""


def api_get(session: requests.Session, path: str, params: dict | None = None) -> Any:
    url = f"{API_BASE}{path}"
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

        # Some APIs return a single result object.
        if pick(payload, "product_id", "productId", "id") is not None:
            return [payload]

    return []


def get_product_id(candidate: dict) -> int | None:
    value = pick(candidate, "product_id", "productId", "id")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def candidate_name(candidate: dict) -> str:
    return str(pick(candidate, "name", "card_name", "product_name", "title") or "")


def candidate_number(candidate: dict) -> str:
    return str(
        pick(
            candidate,
            "number",
            "collector_number",
            "collectorNumber",
            "card_number",
        )
        or ""
    )


def choose_candidate(
    candidates: list[dict],
    card_name: str,
    card_number: str | None,
) -> tuple[dict | None, str]:
    """
    Conservative matching:
      1. exact normalized name + exact collector number
      2. exact normalized name only, but only if there is exactly one candidate
      otherwise -> ambiguous/unmatched

    We deliberately avoid guessing based on fuzzy similarity.
    """
    exact_name = [c for c in candidates if norm(candidate_name(c)) == norm(card_name)]

    if card_number:
        exact = [
            c
            for c in exact_name
            if norm(candidate_number(c)) == norm(card_number)
        ]
        if len(exact) == 1:
            return exact[0], "matched"
        if len(exact) > 1:
            return None, "ambiguous"

    if len(exact_name) == 1:
        return exact_name[0], "matched"
    if len(exact_name) > 1:
        return None, "ambiguous"

    return None, "unmatched"


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


def save_product(cur: psycopg.Cursor, detail: dict, fallback_product_id: int) -> int:
    product_id = get_product_id(detail) or fallback_product_id
    set_name, group_id = set_fields(detail)

    card_name = str(
        pick(detail, "name", "card_name", "product_name", "title") or product_id
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
    source_url = pick(detail, "url", "source_url", "sourceUrl", "page_url", "pageUrl")

    cur.execute(
        """
        INSERT INTO card_product (
            product_id, card_name, set_name, collector_number,
            rarity, image_url, source_url, group_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (product_id) DO UPDATE
        SET card_name = EXCLUDED.card_name,
            set_name = EXCLUDED.set_name,
            collector_number = EXCLUDED.collector_number,
            rarity = EXCLUDED.rarity,
            image_url = EXCLUDED.image_url,
            source_url = EXCLUDED.source_url,
            group_id = EXCLUDED.group_id
        """,
        (
            product_id,
            card_name,
            set_name,
            str(collector_number) if collector_number is not None else None,
            str(rarity) if rarity is not None else None,
            str(image_url) if image_url is not None else None,
            str(source_url) if source_url is not None else None,
            group_id,
        ),
    )
    return product_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sleep", type=float, default=0.8)
    parser.add_argument("--rematch", action="store_true")
    args = parser.parse_args()

    limitless_dsn = os.environ.get("LIMITLESS_DB_DSN")
    tickermint_dsn = os.environ.get("TICKERMINT_DB_DSN")
    if not limitless_dsn or not tickermint_dsn:
        raise SystemExit("Set LIMITLESS_DB_DSN and TICKERMINT_DB_DSN.")

    session = requests.Session()
    session.headers["User-Agent"] = "PokemonDWH-UniversityProject/1.0"

    with psycopg.connect(limitless_dsn) as lconn, psycopg.connect(tickermint_dsn) as tconn:
        with tconn.cursor() as cur:
            cur.execute(DDL)
        tconn.commit()

        with lconn.cursor() as cur:
            cur.execute(
                """
                SELECT card_id, card_name, set_code, card_number
                FROM card
                ORDER BY card_id
                """
            )
            cards = cur.fetchall()

        with tconn.cursor() as tcur:
            for card_id, card_name, set_code, card_number in cards:
                if not args.rematch:
                    tcur.execute(
                        """
                        SELECT 1
                        FROM limitless_card_map
                        WHERE limitless_card_id = %s
                        """,
                        (card_id,),
                    )
                    if tcur.fetchone():
                        continue

                # Name + collector number is usually the strongest search text.
                # set_code is appended as extra information, but matching below
                # stays conservative because TickerMint may expose a set name
                # rather than the same abbreviation used by Limitless.
                parts = [card_name]
                if set_code:
                    parts.append(set_code)
                if card_number:
                    parts.append(card_number)
                query = " ".join(parts)

                payload = api_get(
                    session,
                    "/products/search",
                    params={"q": query, "game": "pokemon"},
                )
                candidates = to_results(payload)
                chosen, status = choose_candidate(
                    candidates,
                    card_name,
                    card_number,
                )

                product_id = None
                note = None

                if chosen is not None:
                    pid = get_product_id(chosen)
                    if pid is None:
                        status = "unmatched"
                        note = "Candidate did not expose a product_id."
                    else:
                        detail = api_get(session, f"/products/{pid}")
                        product_id = save_product(tcur, detail, pid)
                else:
                    note = f"{len(candidates)} search candidate(s). Review manually if needed."

                tcur.execute(
                    """
                    INSERT INTO limitless_card_map (
                        limitless_card_id, product_id, match_status,
                        search_query, matched_at, note
                    )
                    VALUES (%s, %s, %s, %s, now(), %s)
                    ON CONFLICT (limitless_card_id) DO UPDATE
                    SET product_id = EXCLUDED.product_id,
                        match_status = EXCLUDED.match_status,
                        search_query = EXCLUDED.search_query,
                        matched_at = now(),
                        note = EXCLUDED.note
                    """,
                    (card_id, product_id, status, query, note),
                )
                tconn.commit()

                print(
                    f"{card_id}: {card_name} {set_code or ''} {card_number or ''} "
                    f"-> {status} {product_id or ''}"
                )
                time.sleep(args.sleep)


if __name__ == "__main__":
    main()
