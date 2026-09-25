"""Pure tests for the TickermintProductsImporter helpers (no DB, no network)."""

from __future__ import annotations

import pytest

from dvs.api.tickermint_products import (
    _norm,
    _pick_match,
    _product_id,
    _to_results,
    build_search_query,
)


def _c(**kw):
    return kw


# ---------------------------------------------------------------------------
# _norm.
# ---------------------------------------------------------------------------


def test_norm_lowercases_and_strips_punctuation() -> None:
    assert _norm("Pikachu VMAX") == "pikachuvmax"
    assert _norm("Charizard-ex 199/165") == "charizardex199165"
    assert _norm(None) == ""
    assert _norm("") == ""


# ---------------------------------------------------------------------------
# _to_results / _product_id.
# ---------------------------------------------------------------------------


def test_to_results_handles_list_envelope() -> None:
    payload = [_c(product_id=1, name="A"), _c(product_id=2, name="B")]
    assert len(_to_results(payload)) == 2


def test_to_results_handles_results_key_envelope() -> None:
    payload = {"results": [_c(product_id=1)]}
    assert _to_results(payload) == [_c(product_id=1)]


def test_to_results_handles_single_object_envelope() -> None:
    payload = {"product_id": 42, "name": "Pikachu"}
    assert _to_results(payload) == [{"product_id": 42, "name": "Pikachu"}]


def test_to_results_returns_empty_for_unknown_shape() -> None:
    assert _to_results({"not": "a list"}) == []
    assert _to_results("a string") == []


def test_product_id_handles_strings() -> None:
    assert _product_id(_c(product_id="42")) == 42
    assert _product_id(_c(id="99")) == 99
    assert _product_id(_c(product_id="abc")) is None
    assert _product_id(_c()) is None


# ---------------------------------------------------------------------------
# _pick_match: single-tier conservative name match.
# ---------------------------------------------------------------------------


def test_pick_match_returns_first_when_name_matches() -> None:
    c1 = _c(name="Pikachu", product_id=1)
    c2 = _c(name="Pikachu - SVI 58", product_id=2)
    assert _pick_match([c1, c2], "Pikachu") == c1


def test_pick_match_keeps_first_with_embedded_card_number() -> None:
    """TickerMint embeds the card number in candidate names; the first
    prefix-matching candidate wins (no fallback to name-only)."""
    c1 = _c(name="Fezandipiti ex - 288/217", product_id=1)
    c2 = _c(name="Fezandipiti ex - 092/064", product_id=2)
    assert _pick_match([c1, c2], "Fezandipiti ex") == c1


def test_pick_match_rejects_unrelated_names() -> None:
    c1 = _c(name="Pikachu - 58", product_id=1)
    c2 = _c(name="Completely Unrelated", product_id=2)
    assert _pick_match([c1, c2], "Pikachu") == c1


def test_pick_match_returns_none_when_nothing_matches() -> None:
    c1 = _c(name="Completely Unrelated", product_id=1)
    assert _pick_match([c1], "Marill") is None


def test_pick_match_returns_none_for_blank_query() -> None:
    c1 = _c(name="Pikachu", product_id=1)
    assert _pick_match([c1], "") is None
    assert _pick_match([c1], None) is None  # type: ignore[arg-type]


def test_pick_match_returns_none_for_empty_candidate_list() -> None:
    assert _pick_match([], "Pikachu") is None


def test_pick_match_normalizes_case_and_punctuation() -> None:
    c1 = _c(name="Charizard ex - 199/165", product_id=1)
    assert _pick_match([c1], "Charizard EX 199/165") == c1


# ---------------------------------------------------------------------------
# build_search_query: "{card_name} {card_set_number}/{set_number}".
# ---------------------------------------------------------------------------


def test_build_search_query_full_template() -> None:
    assert build_search_query("Pikachu ex", "200", "69") == "Pikachu ex 200/69"


def test_build_search_query_simple() -> None:
    assert build_search_query("Pikachu", "58", "165") == "Pikachu 58/165"


@pytest.mark.parametrize(
    "name, num, denom",
    [
        ("Pikachu", None, "165"),
        ("Pikachu", "58", None),
        ("Pikachu", "", "165"),
        ("Pikachu", "58", ""),
        ("", "58", "165"),
    ],
)
def test_build_search_query_returns_none_on_missing_pieces(
    name: str, num: str | None, denom: str | None
) -> None:
    """Any missing piece -> None. The caller will log + insert NULL row."""
    assert build_search_query(name, num, denom) is None
