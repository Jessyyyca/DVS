"""PokeAPI importer (pokemon + types + abilities + moves).

Per the ERM, this fills:
    pokemon (id, name, base_experience, ..., speed)
    type / ability / move (lookup)
    pokemon_type / pokemon_ability / pokemon_move (m:n)

Endpoint:
    GET https://pokeapi.co/api/v2/pokemon/{id_or_name}
"""

from __future__ import annotations

import asyncio
from typing import Any, Iterable

import aiohttp

from .base import ApiImporter

API_BASE = "https://pokeapi.co/api/v2"

DDL = """
CREATE TABLE IF NOT EXISTS pokemon (
    id              INT PRIMARY KEY,
    name            TEXT NOT NULL,
    base_experience INT,
    height          INT,
    is_default      BOOLEAN,
    weight          INT,
    "order"         INT,
    hp              INT,
    attack          INT,
    defense         INT,
    special_attack  INT,
    special_defense INT,
    speed           INT
);
CREATE INDEX IF NOT EXISTS ix_pokemon_name ON pokemon (name);

CREATE TABLE IF NOT EXISTS pokemon_type (
    pokemon_id INT  NOT NULL REFERENCES pokemon(id) ON DELETE CASCADE,
    type_url   TEXT NOT NULL REFERENCES type(url_id) ON DELETE CASCADE,
    PRIMARY KEY (pokemon_id, type_url)
);
CREATE INDEX IF NOT EXISTS ix_pokemon_type_type ON pokemon_type (type_url);

CREATE TABLE IF NOT EXISTS pokemon_ability (
    pokemon_id  INT NOT NULL REFERENCES pokemon(id) ON DELETE CASCADE,
    ability_url TEXT NOT NULL REFERENCES ability(url_id) ON DELETE CASCADE,
    PRIMARY KEY (pokemon_id, ability_url)
);

CREATE TABLE IF NOT EXISTS pokemon_move (
    pokemon_id INT  NOT NULL REFERENCES pokemon(id) ON DELETE CASCADE,
    move_url   TEXT NOT NULL REFERENCES move(url_id) ON DELETE CASCADE,
    PRIMARY KEY (pokemon_id, move_url)
);
"""


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _stats_by_name(data: dict[str, Any]) -> dict[str, int]:
    """Flatten PokeAPI `stats: [{base_stat, stat: {name}}]` into a name->int map."""
    out: dict[str, int] = {}
    for entry in data.get("stats", []) or []:
        stat = entry.get("stat") or {}
        name = stat.get("name")
        if not name:
            continue
        out[name] = _maybe_int(entry.get("base_stat")) or 0
    return out


class PokeapiImporter(ApiImporter):
    """Imports Pokemon + their types/abilities/moves into the ERM tables."""

    name = "pokeapi"
    api_base_url = f"{API_BASE}/pokemon/ditto"  # cheap default for test()

    async def setup_schema(self) -> None:
        # type / ability / move tables live in src/dvs/schema.sql.
        async with self.pool.acquire() as conn:
            await conn.execute(DDL)

    async def run(
        self,
        *,
        ids: Iterable[int] | None = None,
        names: Iterable[str] | None = None,
        concurrency: int = 4,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        await self.setup_schema()

        id_list = list(ids or [])
        name_list = list(names or [])
        if not id_list and not name_list:
            raise ValueError(
                "Provide at least one of --ids (e.g. 1,2,3) or "
                "--names (e.g. ditto,pikachu)."
            )

        own_session = session is None
        if own_session:
            session = aiohttp.ClientSession(
                headers={"User-Agent": "DVS/0.1"}
            )

        try:
            self.logger.info(
                "fetching %d Pokemon (%d by id, %d by name).",
                len(id_list) + len(name_list),
                len(id_list),
                len(name_list),
            )
            sem = asyncio.Semaphore(concurrency)
            tasks: list[asyncio.Task[int]] = []
            for pid in id_list:
                tasks.append(
                    asyncio.create_task(self._import_id(sem, session, pid))
                )
            for name in name_list:
                tasks.append(
                    asyncio.create_task(self._import_name(sem, session, name))
                )

            results = await asyncio.gather(*tasks, return_exceptions=True)

            saved = 0
            for r in results:
                if isinstance(r, BaseException):
                    self.logger.error("pokemon import failed: %r", r)
                    continue
                saved += r

            self.logger.info("Done. Imported %d Pokemon.", saved)
        finally:
            if own_session:
                await session.close()

    async def _import_id(
        self,
        sem: asyncio.Semaphore,
        session: aiohttp.ClientSession,
        pid: int,
    ) -> int:
        async with sem:
            data = await self.get_json(
                session, f"{API_BASE}/pokemon/{pid}"
            )
        return await self._persist(session, data)

    async def _import_name(
        self,
        sem: asyncio.Semaphore,
        session: aiohttp.ClientSession,
        name: str,
    ) -> int:
        async with sem:
            data = await self.get_json(
                session, f"{API_BASE}/pokemon/{name.lower()}"
            )
        return await self._persist(session, data)

    async def _persist(
        self,
        session: aiohttp.ClientSession,
        data: dict[str, Any],
    ) -> int:
        stats = _stats_by_name(data)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await self._upsert_type_lookup(conn, data.get("types") or [])
                await self._upsert_ability_lookup(
                    conn, data.get("abilities") or []
                )
                await self._upsert_pokemon(conn, data, stats)
                await self._link_types(conn, data)
                await self._link_abilities(conn, data)

                # Moves can be very large (100+ per Pokemon). Fetch lazily
                # only when the caller asked for them. We don't here -- the
                # CLI flag for that lives outside this PR.
                moves_saved = 0

        self.logger.info(
            "%s (id=%s): saved %d move references",
            data.get("name"),
            data.get("id"),
            moves_saved,
        )
        return 1

    async def _upsert_pokemon(
        self,
        conn,
        data: dict[str, Any],
        stats: dict[str, int],
    ) -> None:
        await conn.execute(
            """
            INSERT INTO pokemon (
                id, name, base_experience, height, is_default, weight,
                "order", hp, attack, defense, special_attack,
                special_defense, speed
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7,
                $8, $9, $10, $11, $12, $13
            )
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                base_experience = EXCLUDED.base_experience,
                height = EXCLUDED.height,
                is_default = EXCLUDED.is_default,
                weight = EXCLUDED.weight,
                "order" = EXCLUDED."order",
                hp = EXCLUDED.hp,
                attack = EXCLUDED.attack,
                defense = EXCLUDED.defense,
                special_attack = EXCLUDED.special_attack,
                special_defense = EXCLUDED.special_defense,
                speed = EXCLUDED.speed
            """,
            _maybe_int(data.get("id")),
            data.get("name"),
            _maybe_int(data.get("base_experience")),
            _maybe_int(data.get("height")),
            data.get("is_default"),
            _maybe_int(data.get("weight")),
            _maybe_int(data.get("order")),
            stats.get("hp", 0),
            stats.get("attack", 0),
            stats.get("defense", 0),
            stats.get("special-attack", 0),
            stats.get("special-defense", 0),
            stats.get("speed", 0),
        )

    async def _upsert_type_lookup(
        self,
        conn,
        types: list[dict[str, Any]],
    ) -> None:
        for entry in types:
            type_obj = entry.get("type") or {}
            url = type_obj.get("url")
            name = type_obj.get("name")
            if not url or not name:
                continue
            await conn.execute(
                """
                INSERT INTO type (url_id, name)
                VALUES ($1, $2)
                ON CONFLICT (url_id) DO UPDATE SET name = EXCLUDED.name
                """,
                url,
                name,
            )

    async def _upsert_ability_lookup(
        self,
        conn,
        abilities: list[dict[str, Any]],
    ) -> None:
        for entry in abilities:
            ab = entry.get("ability") or {}
            url = ab.get("url")
            name = ab.get("name")
            if not url or not name:
                continue
            await conn.execute(
                """
                INSERT INTO ability (url_id, name)
                VALUES ($1, $2)
                ON CONFLICT (url_id) DO UPDATE SET name = EXCLUDED.name
                """,
                url,
                name,
            )

    async def _link_types(self, conn, data: dict[str, Any]) -> None:
        for entry in data.get("types") or []:
            type_obj = entry.get("type") or {}
            url = type_obj.get("url")
            if not url:
                continue
            await conn.execute(
                """
                INSERT INTO pokemon_type (pokemon_id, type_url)
                VALUES ($1, $2)
                ON CONFLICT (pokemon_id, type_url) DO NOTHING
                """,
                _maybe_int(data.get("id")),
                url,
            )

    async def _link_abilities(self, conn, data: dict[str, Any]) -> None:
        for entry in data.get("abilities") or []:
            ab = entry.get("ability") or {}
            url = ab.get("url")
            if not url:
                continue
            await conn.execute(
                """
                INSERT INTO pokemon_ability (pokemon_id, ability_url)
                VALUES ($1, $2)
                ON CONFLICT (pokemon_id, ability_url) DO NOTHING
                """,
                _maybe_int(data.get("id")),
                url,
            )


__all__ = ["PokeapiImporter"]