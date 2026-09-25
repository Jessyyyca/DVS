"""Static lookup tables used by the TickerMint importers.

TickerMint indexes products by ``card_number`` in the form
``<card>/<set>`` where ``<set>`` is the **set size** (denominator), e.g.
``"199/165"`` is card 199 in a 165-card set, ``"142/217"`` is card 142
in a 217-card set. The Limitless side uses its own short set codes
(``ASC``, ``MEG``, ``SVI``, ...) that have no meaning to TickerMint.

A search like ``"Charizard ex 165"`` (denominator only) narrows
TickerMint's results to just the SV: Scarlet & Violet 151 set
(``group_id=23237``); a search for ``"Charizard ex 199/165"`` (full
card number) returns exactly the one right product.

So the static map is **Limitless set code -> set denominator string**.
For sets where Limitless has its own printed-set-name that TickerMint
also accepts in queries (rare), we add a name hint as well.

This module is deliberately small and hand-curated. The strategy is:

* Tier 1 query -> ``"name <card>/<denom>"`` (full card number when we
  have both: even more precise).
* Tier 2 query -> ``"name <denom>"`` (denominator narrows the set).
* Tier 3 query -> ``"name"`` (broadest; falls through if we lack a
  mapping).

When the map misses, the importer skips the set tier entirely instead
of emitting the raw Limitless code that TickerMint can't match.

Add a new entry by appending a row whose key is the Limitless code as
it appears in the ``card.set_code`` column, and whose value is the
denominator (the right-hand number in TickerMint's ``card_number``
field). Use a one-shot ``curl`` against the live API to discover the
right value when you're unsure.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Limitless set code -> TickerMint set denominator.
#
# Hand-curated. Verified entries are sourced from the captured responses
# under example_responses/tickermint/products/search/ and the live log
# output of `dvs tickermint-products`. Entries marked TODO need a
# one-shot `curl "https://api.tickermint.cards/products/search?q=<name>
# <denom>&game=pokemon"` probe to confirm.
#
# IMPORTANT: a search for "Fezandipiti ex 217" returns BOTH ASC cards
# (142/217 and 288/217) -- the denominator narrows to the set family,
# not to a specific card. Combine with the card number to disambiguate.
# ---------------------------------------------------------------------------
LIMITLESS_TO_TICKERMINT_DENOM: dict[str, str] = {
    # Mega Evolution family (verified)
    "ASC": "217",   # ME: Ascended Heroes (217 cards)
    "MEG": "132",   # ME01: Mega Evolution (132 cards)
    # SV / Scarlet & Violet era
    "SVI": "165",   # SV: Scarlet & Violet 151 (verified)
    "PAL": "167",   # SV: Paldea Evolved. TODO confirm.
    "OBF": "198",   # SV: Obsidian Flames. TODO confirm.
    "MEW": "165",   # SV: 151 (alternate name; collides with SVI). TODO confirm.
    "PAR": "182",   # SV: Paradox Rift. TODO confirm.
    "TEF": "162",   # SV: Temporal Forces. TODO confirm.
    "TWM": "167",   # SV: Twilight Masquerade. TODO confirm.
    "SFA": "198",   # SV: Shrouded Fable. TODO confirm (probably 198 not 167).
    "SCL": "156",   # SV: Stellar Crown. TODO confirm.
    "POK": "167",   # SV: Prismatic Evolutions. TODO confirm.
    "JTG": "159",   # SV: Journey Together. TODO confirm.
    "SSP": "133",   # SV: Surging Sparks. TODO confirm.
    "PRE": "131",   # SV: Prismatic Evolutions (alt). TODO confirm.
    "SCR": "142",   # SV: Stellar Crown (alt). TODO confirm.
    "PBL": "086",   # SV: Black Bolt. TODO confirm.
    "POR": "133",   # SV: 151 (Promo subset?). TODO confirm.
    "CRI": "160",   # SV: Crimson Haze / Crown. TODO confirm.
    # Sword & Shield era
    "CEL": "215",   # SWSH: Celebrations. TODO confirm.
    "EVS": "237",   # SWSH: Evolving Skies. TODO confirm.
    "FST": "186",   # SWSH: Fusion Strike. TODO confirm.
    "BRS": "186",   # SWSH: Brilliant Stars. TODO confirm.
    "ASR": "189",   # SWSH: Astral Radiance. TODO confirm.
    "LOT": "214",   # SWSH: Lost Origin. TODO confirm.
    "CRE": "230",   # SWSH: Crown Zenith. TODO confirm.
    "DRM": "196",   # SWSH: Dragon Majesty. TODO confirm.
    "SSH": "185",   # SWSH: Sword & Shield Base. TODO confirm.
    "RCL": "216",   # SWSH: Rebel Clash. TODO confirm.
    "DAA": "201",   # SWSH: Darkness Ablaze. TODO confirm.
    "CPA": "201",   # SWSH: Champion's Path. TODO confirm.
    "UNB": "236",   # SWSH: Unified Minds. TODO confirm.
    "UNM": "236",   # SWSH: Unbroken Bonds. TODO confirm.
    "HIF": "159",   # SWSH: Hidden Fates. TODO confirm.
    "CEC": "233",   # SWSH: Cosmic Eclipse. TODO confirm.
    "UPR": "262",   # SWSH: Ultra Prism. TODO confirm.
    "FLI": "131",   # SWSH: Forbidden Light. TODO confirm.
    # Sun & Moon era
    "GEN": "083",   # SM: Generations. TODO confirm.
    "GRI": "111",   # SM: Guardians Rising. TODO confirm.
    "BUS": "114",   # SM: Burning Shadows. TODO confirm.
    "STS": "145",   # SM: Steam Siege. TODO confirm.
    "EVO": "100",   # SM: Evolutions. TODO confirm.
    # XY era
    "XY":  "146",   # XY: XY Base. TODO confirm.
    "ROS": "108",   # XY: Roaring Skies. TODO confirm.
    "PRC": "160",   # XY: Primal Clash. TODO confirm.
    "PHF": "119",   # XY: Phantom Forces. TODO confirm.
    "FFI": "124",   # XY: Flashfire. TODO confirm.
    "RC":  "111",   # XY: Radiant Collection (?). TODO confirm.
    "TK":  "146",   # Trainer Kit subsets. TODO confirm.
}


def _resolve_denominator(set_code: str | None) -> str | None:
    """Return the TickerMint set denominator for a Limitless set_code.

    Returns ``None`` for an unmapped or empty set code. The caller
    decides whether to skip the set tier entirely when this is None
    (the importer falls through to Tier 3 -- name-only search).
    """
    if not set_code:
        return None
    return LIMITLESS_TO_TICKERMINT_DENOM.get(set_code)


def denominator_for(set_code: str | None) -> str | None:
    """Public lookup used by TickermintProductsImporter.

    Same contract as ``_resolve_denominator``; kept as a separate name
    so the importer's import statement is stable even if we add caching
    or normalisation later.
    """
    return _resolve_denominator(set_code)


__all__ = [
    "LIMITLESS_TO_TICKERMINT_DENOM",
    "denominator_for",
]