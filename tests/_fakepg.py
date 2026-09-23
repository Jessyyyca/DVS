"""Minimal asyncpg-compatible stub for idempotency tests.

Stores rows in process memory and mimics the relevant asyncpg API:
- Pool.acquire() -> Connection context manager.
- Connection.execute / fetch / fetchrow / fetchval.
- Connection.transaction() -> context manager.
- UniqueViolationError on conflict.

It does NOT parse SQL -- callers use parameterized queries and the stub
checks PK/unique-key conflicts using the row values it has already stored.
Because we don't parse SQL, the tests must call execute() with strings
that contain the keyword ON CONFLICT (which is what our SQL does) so the
stub can decide to swallow the error.
"""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import Any

import asyncpg

UniqueViolationError = asyncpg.UniqueViolationError


@dataclass
class _Table:
    name: str
    primary_key: tuple[str, ...] = ()
    unique_keys: tuple[tuple[str, ...], ...] = ()
    serial_columns: tuple[str, ...] = ()  # columns to auto-fill when absent
    rows: dict[tuple, dict[str, Any]] = field(default_factory=dict)
    serial_counter: int = 0


class FakeConnection:
    def __init__(self, tables: dict[str, _Table]):
        self._tables = tables

    async def execute(self, query: str, *args: Any) -> str:
        q = " ".join(query.split())
        if q.startswith("CREATE TABLE"):
            return ""
        if q.startswith("INSERT INTO"):
            return await self._insert(q, args)
        if q.startswith("DELETE FROM"):
            return await self._delete(q, args)
        if q.startswith("UPDATE"):
            return await self._update(q, args)
        return ""

    async def _insert(self, q: str, args: tuple[Any, ...]) -> str:
        # q looks like: "INSERT INTO <name> (...) VALUES (...)".
        after = q.split("INSERT INTO", 1)[1].strip()
        name = after.split(" ", 1)[0].strip()
        t = self._tables[name]
        open_paren = q.index("(", q.index("INSERT INTO"))
        close_paren = q.index(")", open_paren)
        cols = [c.strip() for c in q[open_paren + 1 : close_paren].split(",")]
        values = dict(zip(cols, args[: len(cols)]))

        # Auto-fill serial columns when the caller didn't supply them.
        for col in t.serial_columns:
            if col not in values:
                t.serial_counter += 1
                values[col] = t.serial_counter

        pk = tuple(values[c] for c in t.primary_key)
        pk_exists = pk in t.rows

        unique_exists = False
        for uk_cols in t.unique_keys:
            target = tuple(values[c] for c in uk_cols)
            for row in t.rows.values():
                if tuple(row[c] for c in uk_cols) == target:
                    unique_exists = True
                    break
            if unique_exists:
                break

        if (pk_exists or unique_exists) and "ON CONFLICT" not in q:
            raise UniqueViolationError(
                f"dup on {name}: pk={pk_exists} unique={unique_exists}"
            )
        if (pk_exists or unique_exists) and "DO NOTHING" in q:
            return "INSERT 0 0"
        if pk_exists and "DO UPDATE" in q:
            t.rows[pk].update(values)
            return "UPDATE 1"

        # New row.
        t.rows[pk] = values
        return "INSERT 1"

    async def _delete(self, q: str, args: tuple[Any, ...]) -> str:
        after = q.split("DELETE FROM", 1)[1].strip()
        name = after.split(" ", 1)[0].strip()
        t = self._tables[name]
        before = len(t.rows)
        # We only support DELETE WHERE pk = $1.
        if "WHERE" not in q:
            t.rows.clear()
        else:
            col = q.split("=", 1)[1].split("$", 1)[1].split(" ", 1)[0]
            key = tuple(args[0]) if col.endswith("(") else args[0]
            t.rows.pop(key, None)
        return f"DELETE {before - len(t.rows)}"

    async def _update(self, q: str, args: tuple[Any, ...]) -> str:
        return "UPDATE 1"

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        return []

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        q = " ".join(query.split())
        if q.startswith("SELECT 1 FROM") or q.startswith("SELECT 1\nFROM"):
            name = q.split("FROM", 1)[1].split(" ", 1)[0].strip()
            t = self._tables[name]
            for row in t.rows.values():
                if all(row[c] == args[i] for i, c in enumerate(t.primary_key[: len(args)])):
                    return dict(row)
            return None
        if q.startswith("SELECT card_id FROM card"):
            t = self._tables["card"]
            for row in t.rows.values():
                if (
                    row["card_name"].lower() == args[0].lower()
                    and (row["set_code"] or "") == (args[1] or "")
                    and (row["card_number"] or "") == (args[2] or "")
                ):
                    return dict(row)
            return None
        return None

    async def fetchval(self, query: str, *args: Any) -> Any:
        q = " ".join(query.split())
        if q == "SELECT 1":
            return 1
        if q.startswith("INSERT INTO") and "RETURNING" in q:
            returning = q.split("RETURNING", 1)[1].strip().split()[0]
            await self._insert(q, args)
            after = q.split("INSERT INTO", 1)[1].strip()
            name = after.split(" ", 1)[0].strip()
            t = self._tables[name]
            if not t.rows:
                return None
            last_key = max(
                t.rows.keys(),
                key=lambda k: k[0] if k else 0,
            )
            return t.rows[last_key].get(returning)
        if q.startswith("SELECT card_id FROM card"):
            row = await self.fetchrow(query, *args)
            return row["card_id"] if row else None
        if q.startswith("SELECT 1 FROM limitless_card_map"):
            t = self._tables.get("limitless_card_map")
            if not t:
                return None
            for row in t.rows.values():
                if row["limitless_card_id"] == args[0]:
                    return 1
            return None
        if q.startswith("SELECT DISTINCT m.product_id"):
            t = self._tables.get("limitless_card_map")
            if not t:
                return []
            return [row["product_id"] for row in t.rows.values()]
        return None

    @contextmanager
    def transaction(self):
        # Stub: no real transaction. We yield and rely on per-call
        # error semantics; idempotency tests don't depend on rollback.
        yield


class FakePool:
    def __init__(self, tables: dict[str, _Table]):
        self._tables = tables

    @asynccontextmanager
    async def acquire(self):
        yield FakeConnection(self._tables)


def make_pool() -> FakePool:
    """Pool pre-loaded with the DDL schema used by the importers."""
    return FakePool(
        {
            "deck": _Table(
                "deck", primary_key=("deck_id",)
            ),
            "card": _Table(
                "card",
                primary_key=("card_id",),
                unique_keys=(("card_name", "set_code", "card_number"),),
                serial_columns=("card_id",),
            ),
            "deck_card": _Table(
                "deck_card",
                primary_key=("deck_id", "card_id"),
            ),
            "card_product": _Table(
                "card_product", primary_key=("product_id",)
            ),
            "limitless_card_map": _Table(
                "limitless_card_map",
                primary_key=("limitless_card_id",),
            ),
            "printing": _Table(
                "printing", primary_key=("product_id", "printing_type")
            ),
            "daily_price": _Table(
                "daily_price",
                primary_key=("product_id", "printing_type", "price_date"),
            ),
        }
    )