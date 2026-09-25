"""Unit tests for the static set-code lookup."""

from __future__ import annotations

import pytest

from dvs.api.static import (
    LIMITLESS_TO_TICKERMINT_DENOM,
    denominator_for,
)


def test_known_set_codes_map_to_ticker_mint_denominators() -> None:
    """Hand-curated entries from the captured examples must resolve."""
    assert denominator_for("ASC") == "217"
    assert denominator_for("MEG") == "132"
    assert denominator_for("SVI") == "165"


def test_unknown_set_code_returns_none() -> None:
    """Missing entries return None -- callers skip the set tier cleanly."""
    assert denominator_for("NOPE") is None
    assert denominator_for("zz-not-a-set") is None


def test_empty_set_code_returns_none() -> None:
    assert denominator_for("") is None
    assert denominator_for(None) is None


def test_map_is_dict() -> None:
    """Sanity: the public dict is iterable, mutable, and non-empty."""
    assert isinstance(LIMITLESS_TO_TICKERMINT_DENOM, dict)
    assert len(LIMITLESS_TO_TICKERMINT_DENOM) >= 10


def test_denominators_are_digit_strings() -> None:
    """TickerMint denominators are numeric (e.g. '217', '132')."""
    for code, denom in LIMITLESS_TO_TICKERMINT_DENOM.items():
        assert denom.isdigit(), (
            f"denominator for {code!r} is not digit-only: {denom!r}"
        )