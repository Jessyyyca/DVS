"""Limitless playground kept for ad-hoc exploration. Not an importer.

Fetches one tournament + one standings/decklist payload and saves the raw
JSON under example_responses/limitless/ so future work can replay the
parser without hitting the live API.

Run via:
    python -m dvs._limitless_playground
"""

from __future__ import annotations

import asyncio
import json
import os
from pprint import pformat
from typing import Any

import aiohttp

API_BASE = "https://play.limitlesstcg.com/api"


async def _get_json(
    session: aiohttp.ClientSession, url: str, *, params: dict | None = None
) -> Any:
    async with session.get(url, params=params) as r:
        if r.status >= 400:
            body = (await r.text())[:300]
            raise RuntimeError(
                f"Limitless API {r.status} on {r.url}: {body}"
            )
        return await r.json()


async def fetch_limitless_sample(
    tournament_id: str = "6ab0812de905c1db687469ae",
    *,
    listing_limit: int = 5,
    out_dir: str | None = None,
) -> tuple[Any, Any]:
    """Save a tournament listing + one tournament's standings payload.

    The /api/tournaments/{id} detail endpoint is not served (returns 404),
    so the "tournament sample" comes from /api/tournaments?limit=...
    and the "deck sample" comes from /api/tournaments/{id}/standings,
    which is the only path that exposes the decklist payload.
    """
    out_root = out_dir or os.path.join(os.getcwd(), "example_responses")

    async with aiohttp.ClientSession(
        headers={"User-Agent": "DVS/0.1"}
    ) as session:
        listing = await _get_json(
            session,
            f"{API_BASE}/tournaments",
            params={"game": "PTCG", "format": "STANDARD", "limit": listing_limit},
        )
        standings = await _get_json(
            session, f"{API_BASE}/tournaments/{tournament_id}/standings"
        )

    t_path = os.path.join(
        out_root, "limitless", "tournaments", "standard_recent.json"
    )
    s_path = os.path.join(
        out_root, "limitless", "standings", f"{tournament_id}.json"
    )
    os.makedirs(os.path.dirname(t_path), exist_ok=True)
    os.makedirs(os.path.dirname(s_path), exist_ok=True)
    with open(t_path, "w") as f:
        f.write(json.dumps(listing, indent=4))
    with open(s_path, "w") as f:
        f.write(json.dumps(standings, indent=4))

    print(pformat(listing))
    print(pformat(standings))
    return listing, standings


def main() -> None:
    """Save the default sample tournament + standings."""
    asyncio.run(fetch_limitless_sample())


__all__ = ["fetch_limitless_sample", "main"]
