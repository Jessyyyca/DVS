"""Pure tests for the conservative TickerMint candidate matcher."""

from __future__ import annotations

from dvs.api.tickermint_products import (
    candidate_name,
    candidate_number,
    choose_candidate,
    get_product_id,
    pick,
    set_fields,
    to_results,
)


def _c(**kw):
    return kw


def test_pick_returns_first_present_key() -> None:
    assert pick(_c(productId=42, id=99), "product_id", "productId", "id") == 42
    assert pick(_c(id=99), "product_id", "productId", "id") == 99
    assert pick(_c(), "product_id", "productId") is None


def test_get_product_id_handles_strings() -> None:
    assert get_product_id(_c(product_id="42")) == 42
    assert get_product_id(_c(productId="abc")) is None


def test_candidate_name_and_number() -> None:
    assert candidate_name(_c(card_name="Pikachu")) == "Pikachu"
    assert candidate_number(_c(collector_number="58/102")) == "58/102"


def test_to_results_handles_envelopes() -> None:
    assert len(to_results({"results": [_c(id=1), _c(id=2)]})) == 2
    assert len(to_results([_c(id=1)])) == 1
    assert to_results({"not": "a list"}) == []
    # Single product envelope.
    assert to_results({"product_id": 1, "name": "X"}) == [
        {"product_id": 1, "name": "X"}
    ]


def test_set_fields_handles_dict_and_scalar() -> None:
    name, gid = set_fields(
        {"name": "X", "set": {"name": "Base", "group_id": 7}}
    )
    assert name == "Base"
    assert gid == 7

    name, gid = set_fields({"name": "Y", "group_id": "9"})
    assert name is None
    assert gid == 9

    name, gid = set_fields({"name": "Z"})
    assert name is None and gid is None


def test_choose_candidate_prefers_name_plus_number() -> None:
    c1 = _c(name="Pikachu", number="58")
    c2 = _c(name="Pikachu", number="58")
    chosen, status = choose_candidate([c1, c2], "Pikachu", "58")
    assert status == "ambiguous"


def test_choose_candidate_unique_number_match() -> None:
    c1 = _c(name="Pikachu", number="58")
    chosen, status = choose_candidate([c1], "Pikachu", "58")
    assert status == "matched"
    assert chosen is c1


def test_choose_candidate_unique_name_only() -> None:
    c1 = _c(name="Pikachu", number="")
    chosen, status = choose_candidate([c1], "Pikachu", None)
    assert status == "matched"
    assert chosen is c1


def test_choose_candidate_unmatched_when_empty() -> None:
    _, status = choose_candidate([], "Pikachu", "58")
    assert status == "unmatched"