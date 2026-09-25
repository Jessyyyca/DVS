"""Unified CLI: dvs <limitless|tickermint-products|tickermint-prices|generate-sql>.

Each subcommand accepts shared rate-limit + concurrency flags,
plus subcommand-specific arguments. Pass --test to only probe the API
and the DB without doing the real import. Pass `generate-sql` to emit
the schema bootstrap SQL for manual psql / migration runs.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date
from typing import Any

import aiohttp

from .api import (
    LimitlessImporter,
    PokeapiImporter,
    RateLimit,
    TickermintPricesImporter,
    TickermintProductsImporter,
)
from .db import close_pool, get_pool
from .schema import read_schema


def _rate_args(p: argparse.ArgumentParser) -> None:
    """Attach the shared rate-limit + concurrency flags."""
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--rate-burst", type=int, default=60)
    p.add_argument("--rate-window", type=float, default=60.0)
    p.add_argument("--max-per-hour", type=int, default=None)
    p.add_argument("--max-per-day", type=int, default=None)
    p.add_argument(
        "--test",
        action="store_true",
        help="Smoke-test the API + DB and exit (skip the real import).",
    )


def _rate_limit(args: argparse.Namespace) -> RateLimit:
    return RateLimit(
        burst=args.rate_burst,
        window_seconds=args.rate_window,
        max_per_hour=args.max_per_hour,
        max_per_day=args.max_per_day,
    )


def _configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    # basicConfig is a no-op when the root logger already has handlers
    # (aiohttp / asyncpg may have installed one on import). Force the level
    # so --log-level DEBUG actually surfaces DEBUG from dvs.api.* loggers.
    logging.getLogger().setLevel(
        getattr(logging, level.upper(), logging.INFO)
    )


def _log_level_args(p: argparse.ArgumentParser) -> None:
    """Attach the --log-level flag to a subparser."""
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        help="Logging level (default: INFO).",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dvs", description=__doc__)
    sub = parser.add_subparsers(dest="api", required=True)

    p_lim = sub.add_parser(
        "limitless", help="Import Limitless tournament decklists."
    )
    p_lim.add_argument("--from-date", type=date.fromisoformat, required=True)
    p_lim.add_argument(
        "--to-date", type=date.fromisoformat, default=date.today()
    )
    p_lim.add_argument("--format", default="STANDARD")
    p_lim.add_argument("--max-pages", type=int, default=100)
    _rate_args(p_lim)
    _log_level_args(p_lim)

    p_prod = sub.add_parser(
        "tickermint-products",
        help="Import TickerMint products for every Limitless card_name.",
    )
    _rate_args(p_prod)
    _log_level_args(p_prod)

    p_prices = sub.add_parser(
        "tickermint-prices",
        help="Import TickerMint historical prices for matched products.",
    )
    p_prices.add_argument("--from-date", type=date.fromisoformat, default=None)
    p_prices.add_argument("--to-date", type=date.fromisoformat, default=None)
    _rate_args(p_prices)
    _log_level_args(p_prices)

    p_poke = sub.add_parser(
        "pokeapi", help="Import Pokemon + types + abilities from PokeAPI."
    )
    p_poke.add_argument(
        "--ids",
        type=lambda s: [int(x) for x in s.split(",") if x.strip()],
        default=None,
        help="Comma-separated Pokemon ids (e.g. 1,4,7).",
    )
    p_poke.add_argument(
        "--names",
        type=lambda s: [x.strip() for x in s.split(",") if x.strip()],
        default=None,
        help="Comma-separated Pokemon names (e.g. ditto,pikachu).",
    )
    p_poke.add_argument(
        "--from-id",
        type=int,
        default=None,
        help="Inclusive lower bound on id (used when neither --ids nor --names).",
    )
    p_poke.add_argument(
        "--to-id",
        type=int,
        default=None,
        help="Inclusive upper bound on id (used when neither --ids nor --names).",
    )
    _rate_args(p_poke)
    _log_level_args(p_poke)

    p_sql = sub.add_parser(
        "generate-sql",
        help="Emit the schema bootstrap SQL (stdout or --out).",
    )
    p_sql.add_argument(
        "--out",
        type=argparse.FileType("w", encoding="utf-8"),
        default=sys.stdout,
        help="Write SQL to this file instead of stdout.",
    )
    _log_level_args(p_sql)

    return parser


async def _run_limited(args: argparse.Namespace) -> None:
    pool = await get_pool()
    importer = LimitlessImporter(pool, rate_limit=_rate_limit(args))
    if args.test:
        await importer.test()
        await close_pool()
        return
    async with aiohttp.ClientSession(
        headers={"User-Agent": "DVS/0.1"}
    ) as session:
        await importer.run(
            from_date=args.from_date,
            to_date=args.to_date,
            format=args.format,
            max_pages=args.max_pages,
            concurrency=args.concurrency,
            session=session,
        )
    await close_pool()


async def _run_products(args: argparse.Namespace) -> None:
    pool = await get_pool()
    importer = TickermintProductsImporter(pool, rate_limit=_rate_limit(args))
    if args.test:
        await importer.test()
        await close_pool()
        return
    async with aiohttp.ClientSession(
        headers={"User-Agent": "DVS/0.1"}
    ) as session:
        await importer.run(
            concurrency=args.concurrency,
            session=session,
        )
    await close_pool()


async def _run_prices(args: argparse.Namespace) -> None:
    pool = await get_pool()
    importer = TickermintPricesImporter(pool, rate_limit=_rate_limit(args))
    if args.test:
        await importer.test()
        await close_pool()
        return
    async with aiohttp.ClientSession(
        headers={"User-Agent": "DVS/0.1"}
    ) as session:
        await importer.run(
            from_date=args.from_date,
            to_date=args.to_date,
            concurrency=args.concurrency,
            session=session,
        )
    await close_pool()


async def _run_pokeapi(args: argparse.Namespace) -> None:
    pool = await get_pool()
    importer = PokeapiImporter(pool, rate_limit=_rate_limit(args))
    if args.test:
        await importer.test()
        await close_pool()
        return

    ids: list[int] | None = args.ids
    names: list[str] | None = args.names
    if ids is None and names is None:
        if args.from_id is None and args.to_id is None:
            raise SystemExit(
                "Provide --ids, --names, or both --from-id and --to-id."
            )
        lo = args.from_id if args.from_id is not None else 1
        hi = args.to_id if args.to_id is not None else lo
        ids = list(range(lo, hi + 1))

    async with aiohttp.ClientSession(
        headers={"User-Agent": "DVS/0.1"}
    ) as session:
        await importer.run(
            ids=ids,
            names=names,
            concurrency=args.concurrency,
            session=session,
        )
    await close_pool()


_RUNNERS: dict[str, Any] = {
    "limitless": _run_limited,
    "tickermint-products": _run_products,
    "tickermint-prices": _run_prices,
    "pokeapi": _run_pokeapi,
}


def _run_generate_sql(args: argparse.Namespace) -> None:
    """Synchronous: write schema.sql to args.out (stdout by default)."""
    schema = read_schema()
    args.out.write(schema)
    if args.out is not sys.stdout:
        args.out.close()


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.log_level)
    if args.api == "generate-sql":
        _run_generate_sql(args)
        return
    runner = _RUNNERS[args.api]
    try:
        asyncio.run(runner(args))
    except KeyboardInterrupt:
        raise SystemExit(130)


__all__ = ["main"]