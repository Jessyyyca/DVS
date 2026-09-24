"""Pure tests for the TickerMint candidate filter."""

from __future__ import annotations

from dvs.api.tickermint_products import (
    candidate_name,
    candidate_number,
    filter_candidates,
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


def test_filter_candidates_unmatched_when_empty() -> None:
    assert filter_candidates([], "Pikachu", "58") == []


def test_filter_candidates_keeps_only_name_matches() -> None:
    """Candidates with a different name are dropped, even with the right number."""
    c1 = _c(name="Pikachu", number="58")
    c2 = _c(name="Raichu", number="58")
    out = filter_candidates([c1, c2], "Pikachu", "58")
    assert out == [(c1, "exact_number")]


def test_filter_candidates_tags_exact_number_above_exact_name() -> None:
    """When at least one candidate lines up on number, only those are kept."""
    c1 = _c(name="Pikachu", number="58")
    c2 = _c(name="Pikachu", number="99")
    out = filter_candidates([c1, c2], "Pikachu", "58")
    assert out == [(c1, "exact_number")]


def test_filter_candidates_falls_back_to_exact_name() -> None:
    """No number match -> all name-match candidates kept as exact_name."""
    c1 = _c(name="Pikachu", number="")
    c2 = _c(name="Pikachu", number="3")
    out = filter_candidates([c1, c2], "Pikachu", None)
    kinds = [kind for _, kind in out]
    assert kinds == ["exact_name", "exact_name"]
    assert {c["name"] for c, _ in out} == {"Pikachu"}


def test_filter_candidates_returns_many_when_ambiguous() -> None:
    """1:N: the whole pile survives, never collapses to a single row."""
    c1 = _c(name="Wiglett", number="47")
    c2 = _c(name="Wiglett", number="47")
    c3 = _c(name="Wiglett", number="47")
    out = filter_candidates([c1, c2, c3], "Wiglett", "47")
    assert len(out) == 3
    assert all(kind == "exact_number" for _, kind in out)