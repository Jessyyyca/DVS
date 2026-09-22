import asyncio
from typing import Any
import aiohttp
from pprint import pformat
import json
import os

async def get_pokemon():
    extra_path = "pokemon/vulpix"
    url = f"https://pokeapi.co/api/v2/{extra_path}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            print(pformat(data))

            # convert data to json
            json_data = json.dumps(data, indent=4)

            # create path example_responses/pokeapi/pokemon/<pokomen_name>.json
            path = os.path.join(os.getcwd(), "example_responses/pokeapi", extra_path.replace("/", "_") + ".json")
            os.makedirs(os.path.dirname(path), exist_ok=True)

            # save
            with open(path, "w") as f:
                f.write(json_data)

async def get_tickermint():
    search = "charizard ex 199/165"
    search_encoded = aiohttp.helpers.quote(search)
    url = f"https://api.tickermint.cards/products/search?q={search_encoded}"
    data = await get_as_dict(url)
    print(pformat(data))
    d = json.dumps(data, indent=4)

    # create path example_responses/tickermint/products/search/charizard_ex_199_165.json
    path = os.path.join(os.getcwd(), "example_responses/tickermint/products/search", search.replace(" ", "_"), ".json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(d)

async def get_as_dict(url: str) -> dict[str, Any]:
    """makes a GET request to a given url returning it as a dict (if possible, otherwise it fails)"""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            return data

if __name__ == "__main__":
    asyncio.run(get_tickermint())