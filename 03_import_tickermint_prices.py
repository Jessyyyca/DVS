#!/usr/bin/env python3
"""
03_import_tickermint_prices.py

Imports daily historical TickerMint market prices for products already matched
by 02_match_tickermint_products.py.

Stores only:
  PRINTING(product_id, printing_type)
  DAILY_PRICE(product_id, printing_type, price_date, market_price)

Requirements:
    pip install requests "psycopg[binary]"

Example:
    export TICKERMINT_DB_DSN="postgresql://postgres:postgres@localhost:5432/tickermint_source"
    python 03_import_tickermint_prices.py --from-date 2024-02-01
"""

import argparse
import os
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

import psycopg
import requests

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
        REFERENCES printing(product_id, printing_type)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_daily_price_date
    ON daily_price (price_date);
"""


def api_get(session: requests.Session, path: str) -> Any:
    url = f"{API_BASE}{path}"
    for attempt in range(6):
        r = session.get(url, timeout=45)

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


DATE_KEYS = ("date", "price_date", "priceDate", "day", "snapshot_date")
PRICE_KEYS = (
    "market_price",
    "marketPrice",
    "market",
    "price",
)
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
    """
    TickerMint documents the endpoint as 'daily market price per printing'.
    This walker accepts both common forms:
      [{date, printing, market_price}, ...]
    and
      {"Normal": [{date, market_price}, ...], "Holofoil": [...]}

    If TickerMint changes the envelope but keeps those semantic fields, the
    parser still works.
    """
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", type=date.fromisoformat, default=None)
    parser.add_argument("--to-date", type=date.fromisoformat, default=None)
    parser.add_argument("--sleep", type=float, default=0.55)
    args = parser.parse_args()

    dsn = os.environ.get("TICKERMINT_DB_DSN")
    if not dsn:
        raise SystemExit("Set TICKERMINT_DB_DSN.")

    session = requests.Session()
    session.headers["User-Agent"] = "PokemonDWH-UniversityProject/1.0"

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT m.product_id
                FROM limitless_card_map m
                WHERE m.match_status = 'matched'
                  AND m.product_id IS NOT NULL
                ORDER BY m.product_id
                """
            )
            product_ids = [row[0] for row in cur.fetchall()]

        for product_id in product_ids:
            payload = api_get(
                session,
                f"/products/{product_id}/prices",
            )
            rows = list(iter_price_rows(payload))

            if not rows:
                print(
                    f"WARNING: product {product_id}: no price rows parsed. "
                    "Inspect the endpoint JSON/OpenAPI before changing the parser."
                )
                continue

            saved = 0
            with conn.cursor() as cur:
                for printing_type, price_date, market_price in rows:
                    if args.from_date and price_date < args.from_date:
                        continue
                    if args.to_date and price_date > args.to_date:
                        continue

                    cur.execute(
                        """
                        INSERT INTO printing (product_id, printing_type)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (product_id, printing_type),
                    )

                    cur.execute(
                        """
                        INSERT INTO daily_price (
                            product_id, printing_type, price_date, market_price
                        )
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (product_id, printing_type, price_date)
                        DO UPDATE
                        SET market_price = EXCLUDED.market_price
                        """,
                        (
                            product_id,
                            printing_type,
                            price_date,
                            market_price,
                        ),
                    )
                    saved += 1

            conn.commit()
            print(f"{product_id}: saved {saved} daily price rows")
            time.sleep(args.sleep)


if __name__ == "__main__":
    main()
