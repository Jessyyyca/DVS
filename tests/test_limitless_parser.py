"""Pure-parser tests for Limitless and TickerMint payloads (no network, no DB)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from dvs.api.limitless import iter_card_records, make_deck_id, parse_date
from dvs.api.tickermint_prices import iter_price_rows, looks_like_printing_label


def test_parse_date_strips_z() -> None:
    assert parse_date("2026-09-12T15:00:00Z") == date(2026, 9, 12)


def test_make_deck_id_is_stable() -> None:
    a = make_deck_id("evt-1", "player-1")
    b = make_deck_id("evt-1", "player-1")
    assert a == b


def test_iter_card_records_recurses_nested_lists() -> None:
    payload = {
        "deck": [
            {"name": "Pikachu", "set": "base1", "number": "58", "count": 2},
            {"name": "Ultra Ball", "set": "base1", "number": "82", "quantity": 1},
        ]
    }
    rows = list(iter_card_records(payload))
    assert {(r["name"], r["quantity"]) for r in rows} == {
        ("Pikachu", 2),
        ("Ultra Ball", 1),
    }


def test_iter_card_records_falls_back_to_quantity_one() -> None:
    payload = [{"name": "Mewtwo", "set": "base1", "number": "10"}]
    rows = list(iter_card_records(payload))
    assert rows == [
        {"name": "Mewtwo", "set": "base1", "number": "10", "quantity": 1}
    ]


@pytest.mark.parametrize(
    "key, expected",
    [
        ("Normal", True),
        ("Holofoil", True),
        ("Reverse Holo", True),
        ("reverse_holo", True),
        ("1st Edition", True),
        ("year", False),
    ],
)
def test_looks_like_printing_label(key: str, expected: bool) -> None:
    assert looks_like_printing_label(key) is expected


def test_iter_price_rows_flat() -> None:
    payload = [
        {"date": "2024-02-01", "printing": "Normal", "market_price": "1.23"},
        {"date": "2024-02-02", "printing": "Holofoil", "market_price": "5.5"},
    ]
    out = sorted(iter_price_rows(payload))
    assert out == [
        ("Holofoil", date(2024, 2, 2), Decimal("5.5")),
        ("Normal", date(2024, 2, 1), Decimal("1.23")),
    ]


def test_iter_price_rows_grouped() -> None:
    payload = {
        "Normal": [{"date": "2024-02-01", "market_price": "1.0"}],
        "Holofoil": [
            {"date": "2024-02-01", "market_price": "3.0"},
            {"date": "2024-02-02", "market_price": "3.5"},
        ],
    }
    out = sorted(iter_price_rows(payload))
    assert out == [
        ("Holofoil", date(2024, 2, 1), Decimal("3.0")),
        ("Holofoil", date(2024, 2, 2), Decimal("3.5")),
        ("Normal", date(2024, 2, 1), Decimal("1.0")),
    ]