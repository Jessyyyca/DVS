"""Tests for the Limitless deck INSERT -- covers wins/losses/ties/archtype.

Runs against the in-memory fake pool in tests/_fakepg.py so no DB is needed.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from dvs.api.base import RateLimit
from dvs.api.limitless import LimitlessImporter

from ._fakepg import make_pool


def _rate_limit() -> RateLimit:
    return RateLimit(burst=1000, window_seconds=1.0)


def _standing(**kw):
    base = {
        "player": "alice",
        "decklist": [{"name": "Pikachu", "set": "base1", "number": "58", "count": 1}],
    }
    base.update(kw)
    return base


@pytest.mark.asyncio
async def test_persist_writes_wins_losses_ties_placings() -> None:
    pool = make_pool()
    imp = LimitlessImporter(pool, rate_limit=_rate_limit())
    tournament_id = "evt-1"
    event_date = dt.date(2026, 1, 1)

    standings = [
        _standing(
            player="alice",
            wins=8,
            losses=2,
            ties=0,
            placement=3,
            deck_archetype={"id": "charizard-ex", "name": "Charizard ex"},
        ),
    ]

    async with pool.acquire() as conn:
        decks, rows = await imp._persist_tournament(
            conn, tournament_id, event_date, "STANDARD", standings
        )

    assert decks == 1
    assert rows == 1
    deck_row = next(iter(pool._tables["deck"].rows.values()))
    assert deck_row["player_id"] == "alice"
    assert deck_row["wins"] == 8
    assert deck_row["losses"] == 2
    assert deck_row["ties"] == 0
    assert deck_row["placings"] == 3
    assert deck_row["deck_archtype_id"] == "charizard-ex"
    assert deck_row["deck_archtype_name"] == "Charizard ex"
    assert deck_row["play_date"] == event_date


@pytest.mark.asyncio
async def test_persist_handles_missing_wlt_and_string_archtype() -> None:
    """Standing without wins/losses/ties must still insert cleanly."""
    pool = make_pool()
    imp = LimitlessImporter(pool, rate_limit=_rate_limit())

    standings = [
        _standing(player="bob", deck_archetype="rogue-deck"),
    ]

    async with pool.acquire() as conn:
        decks, rows = await imp._persist_tournament(
            conn, "evt-2", dt.date(2026, 2, 1), "STANDARD", standings
        )

    assert decks == 1 and rows == 1
    deck_row = next(iter(pool._tables["deck"].rows.values()))
    assert deck_row["player_id"] == "bob"
    assert deck_row["wins"] is None
    assert deck_row["losses"] is None
    assert deck_row["ties"] is None
    assert deck_row["placings"] is None
    # String archetype -> archtype_name only, id stays None.
    assert deck_row["deck_archtype_name"] == "rogue-deck"
    assert deck_row["deck_archtype_id"] is None


@pytest.mark.asyncio
async def test_persist_idempotent_on_rerun() -> None:
    """Running persist twice with the same standing must not duplicate rows
    and must update the latest wins/losses."""
    pool = make_pool()
    imp = LimitlessImporter(pool, rate_limit=_rate_limit())
    standings = [
        _standing(player="alice", wins=4, losses=3, ties=0, placement=5),
    ]

    async with pool.acquire() as conn:
        await imp._persist_tournament(
            conn, "evt-3", dt.date(2026, 3, 1), "STANDARD", standings
        )
        await imp._persist_tournament(
            conn, "evt-3", dt.date(2026, 3, 1), "STANDARD",
            [
                _standing(
                    player="alice", wins=7, losses=1, ties=0, placement=1
                )
            ],
        )

    assert len(pool._tables["deck"].rows) == 1
    deck_row = next(iter(pool._tables["deck"].rows.values()))
    assert deck_row["wins"] == 7
    assert deck_row["placings"] == 1


@pytest.mark.asyncio
async def test_persist_skips_standing_without_decklist() -> None:
    pool = make_pool()
    imp = LimitlessImporter(pool, rate_limit=_rate_limit())
    standings = [
        _standing(player="alice"),
        _standing(player="bob", decklist=None),
    ]

    async with pool.acquire() as conn:
        decks, rows = await imp._persist_tournament(
            conn, "evt-4", dt.date(2026, 4, 1), "STANDARD", standings
        )

    assert decks == 1
    assert rows == 1
    # Only Alice's row.
    assert len(pool._tables["deck"].rows) == 1