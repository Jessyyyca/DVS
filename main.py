import asyncio
import aiohttp
from pprint import pformat
import json
import os

async def main():
    extra_path = "pokemon/ditto"
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
if __name__ == "__main__":
    asyncio.run(main())