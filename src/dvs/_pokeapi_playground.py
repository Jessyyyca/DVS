"""PokeAPI playground kept for ad-hoc exploration. Not an importer."""

from __future__ import annotations

import asyncio
import json
import os
from pprint import pformat
from typing import Any

import aiohttp.helpers

BASE_URL = "https://pokeapi.co/api/v2"


async def _get_as_dict(url: str) -> dict[str, Any]:
    """GET a URL, return parsed JSON or raise."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            r.raise_for_status()
            return await r.json()


async def get_pokemon(name: str, *, out_dir: str | None = None) -> dict[str, Any]:
    """Fetch a Pokemon and save the response under example_responses/pokeapi."""
    extra_path = f"pokemon/{name}"
    url = f"{BASE_URL}/{extra_path}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            r.raise_for_status()
            data = await r.json()
    print(pformat(data))

    out_root = out_dir or os.path.join(os.getcwd(), "example_responses")
    path = os.path.join(out_root, "pokeapi", extra_path.replace("/", "_") + ".json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(json.dumps(data, indent=4))
    return data


async def search_tickermint(
    query: str, *, out_dir: str | None = None
) -> dict[str, Any]:
    """Hit TickerMint search, save under example_responses/tickermint/..."""
    encoded = aiohttp.helpers.quote(query)
    url = f"https://api.tickermint.cards/products/search?q={encoded}"
    data = await _get_as_dict(url)
    print(pformat(data))

    out_root = out_dir or os.path.join(os.getcwd(), "example_responses")
    leaf = query.replace(" ", "_")
    path = os.path.join(
        out_root, "tickermint", "products", "search", leaf, ".json"
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(json.dumps(data, indent=4))
    return data


def main() -> None:
    """Run a default exploration (TickerMint charizard search)."""
    asyncio.run(search_tickermint("charizard ex 199/165"))


__all__ = ["get_pokemon", "search_tickermint", "main"]