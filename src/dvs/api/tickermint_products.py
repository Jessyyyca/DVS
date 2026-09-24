"""Match Limitless cards to TickerMint products (was 02_...)."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import aiohttp

from .base import ApiImporter

API_BASE = "https://api.tickermint.cards"

DDL = """
CREATE TABLE IF NOT EXISTS card_product (
    product_id BIGINT PRIMARY KEY,
    card_name TEXT NOT NULL,
    set_name TEXT NULL,
    collector_number TEXT NULL,
    rarity TEXT NULL,
    image_url TEXT NULL,
    source_url TEXT NULL,
    group_id BIGINT NULL
);

-- 1:N: one Limitless card identity can map to many TickerMint products.
-- The matcher wipes existing rows for a card_id before re-inserting.
-- match_kind is 'exact_number' (name + collector number match),
-- 'exact_name' (name matches after normalization), or 'fuzzy' (rapidfuzz
-- fallback). similarity is non-null only for 'fuzzy' rows.
CREATE TABLE IF NOT EXISTS limitless_card_map (
    limitless_card_id BIGINT NOT NULL REFERENCES card(card_id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL REFERENCES card_product(product_id) ON DELETE CASCADE,
    match_kind TEXT NOT NULL CHECK (
        match_kind IN ('exact_number', 'exact_name', 'fuzzy')
    ),
    similarity INT CHECK (
        similarity IS NULL OR (similarity BETWEEN 0 AND 100)
    ),
    search_query TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (limitless_card_id, product_id)
);
"""


def norm(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def pick(obj: dict, *keys: str) -> Any:
    for key in keys:
        if key in obj and obj[key] not in (None, ""):
            return obj[key]
    return None


# Minimum rapidfuzz score (0..100) for a fuzzy match to be persisted.
# Higher = stricter; 70 is a common default that keeps common typos out
# while still matching "Marill" vs "Marill - 083/217 (Friend Ball)".
FUZZY_THRESHOLD = 70


def _number_matches(target: str, candidate: str) -> bool:
    """Compare two collector numbers forgiving leading-zero padding.

    Only the *leading digit run* of each is examined, so '83' matches
    '083/217' (Limiterless pads numbers to 3 digits; TickerMint includes
    the set total). '1' vs '11' is rejected because the leading digits of
    '11' are '11', not '1'.
    """
    def leading(text: str) -> str:
        digits = re.sub(r"[^0-9]", "", text).lstrip("0")
        return digits

    t = leading(target)
    c = leading(candidate)
    if not t or not c:
        return False
    if len(t) < len(c):
        return t == c[: len(t)]
    if len(t) > len(c):
        return t[: len(c)] == c
    return t == c


def _name_prefix_score(target: str, candidate: str) -> int:
    """Percent score for 'target is the leading token block of candidate'.

    TickerMint appends ` - 083/217 (Friend Ball)` style suffixes; we strip
    the trailing `NNN/NNN` collector number and parenthesised variant,
    then check whether every whitespace-delimited word of target appears
    in order at the start of the cleaned candidate. Score is the ratio of
    target words that landed, weighted by length match -- 100 when the
    cleaned candidate equals the target exactly, with partial credit for
    sub-token matches (so 'Marill' vs 'MarillFriendBall' still scores
    high). Returns 0 when the leading-word check fails.
    """
    def clean(text: str) -> list[str]:
        # Strip '<name> - NNN/NNN (variant)' tail.
        head = re.split(r"\s*-\s*\d", text, maxsplit=1)[0]
        # Drop parentheses-and-after.
        head = re.sub(r"\(.*", "", head)
        # Collapse remaining whitespace and split on it.
        return re.findall(r"[a-z0-9]+", head.lower())

    tgt_words = clean(target)
    if not tgt_words:
        return 0
    cand_words = clean(candidate)

    matched = 0
    i = 0
    for w in tgt_words:
        # Walk candidate words looking for the next one that starts with w.
        # Substring-only (e.g. 'Marill' should match 'MarillFriendBall' as
        # the leading block, not just as an equal token).
        while i < len(cand_words):
            if cand_words[i].startswith(w):
                matched += 1
                i += 1
                break
            i += 1
        else:
            break  # ran out of candidate words

    return int(round(100 * matched / len(tgt_words)))


def to_results(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("results", "products", "data", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        if pick(payload, "product_id", "productId", "id") is not None:
            return [payload]
    return []


def get_product_id(candidate: dict) -> int | None:
    value = pick(candidate, "product_id", "productId", "id")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def candidate_name(c: dict) -> str:
    return str(pick(c, "name", "card_name", "product_name", "title") or "")


def candidate_number(c: dict) -> str:
    return str(
        pick(
            c,
            "number",
            "collector_number",
            "collectorNumber",
            "card_number",
        )
        or ""
    )


# TickerMint's /products/search payload typically exposes every field
# card_product needs (name, set_name, group_id, collector_number, rarity,
# image_url). When those keys are present we can persist directly
# without an extra /products/{pid} GET, which is the dominant cost
# during a rematch against many cards.
_SEARCH_KEYS = ("name", "set_name", "group_id", "rarity")


def _search_payload_sufficient(candidate: dict) -> bool:
    """True when the search response carries all fields _save_product reads."""
    return all(k in candidate for k in _SEARCH_KEYS)


def filter_candidates(
    candidates: list[dict],
    card_name: str,
    card_number: str | None,
    *,
    logger: logging.Logger | None = None,
) -> list[tuple[dict, str, int | None]]:
    """Score each candidate and bucket it as exact_number / exact_name / fuzzy.

    Returns (candidate, match_kind, similarity) tuples. similarity is
    non-null only for 'fuzzy' rows. Tiers, in order of preference:

    1. exact_number: normalized candidate name == card name AND the
       leading digits of the candidate's collector number equal the
       Limitless card_number (handles '83' vs '083/217' numbering).
    2. exact_name: case-insensitive normalized name match.
    3. fuzzy: leading-token prefix score >= FUZZY_THRESHOLD; catches
       'Marill' vs 'Marill - 083/217 (Friend Ball)' without false-
       matching unrelated cards.

    `logger` is optional; when provided, DEBUG lines are emitted for each
    candidate decision (exact / fuzzy / dropped) so the cascade is
    traceable without changing any returned behaviour.
    """
    def d(msg: str, *args: Any) -> None:
        if logger is not None and logger.isEnabledFor(logging.DEBUG):
            logger.debug(msg, *args)

    target_name = norm(card_name)
    target_number = str(card_number or "").strip()

    exact_name: list[dict] = []
    fuzzy_pool: list[dict] = []

    for c in candidates:
        if not isinstance(c, dict):
            d("filter_candidates skip: candidate is not a dict")
            continue
        raw_name = candidate_name(c)
        if not raw_name:
            d("filter_candidates skip: empty candidate name for %r", c)
            continue
        pid = get_product_id(c)
        if norm(raw_name) == target_name:
            exact_name.append(c)
            d(
                "filter_candidates exact_name hit: pid=%s name=%r",
                pid, raw_name,
            )
        else:
            score = _name_prefix_score(card_name, raw_name)
            if score >= FUZZY_THRESHOLD:
                fuzzy_pool.append((c, score))
                d(
                    "filter_candidates fuzzy hit: pid=%s name=%r score=%d",
                    pid, raw_name, score,
                )
            else:
                d(
                    "filter_candidates drop: pid=%s name=%r score=%d "
                    "< threshold %d",
                    pid, raw_name, score, FUZZY_THRESHOLD,
                )

    if exact_name and target_number:
        with_number = [
            c
            for c in exact_name
            if _number_matches(target_number, candidate_number(c))
        ]
        d(
            "filter_candidates exact_name -> exact_number: "
            "%d/%d matched number %r",
            len(with_number), len(exact_name), target_number,
        )
        if with_number:
            return [(c, "exact_number", None) for c in with_number]
    if exact_name:
        d(
            "filter_candidates exact_name tier: %d candidate(s) without "
            "matching number",
            len(exact_name),
        )
        return [(c, "exact_name", None) for c in exact_name]

    # Fuzzy tier: rank by prefix score desc, ties by product_id asc.
    fuzzy_pool.sort(
        key=lambda pair: (-pair[1], pair[0].get("product_id", 0))
    )
    d(
        "filter_candidates fuzzy tier: %d candidate(s) "
        "after dropping below threshold %d",
        len(fuzzy_pool), FUZZY_THRESHOLD,
    )
    return [(c, "fuzzy", s) for c, s in fuzzy_pool]


def set_fields(detail: dict) -> tuple[str | None, int | None]:
    raw_set = pick(detail, "set", "set_info", "group")
    if isinstance(raw_set, dict):
        set_name = pick(raw_set, "name", "set_name", "title")
        group_id = pick(raw_set, "group_id", "groupId", "id")
    else:
        set_name = raw_set
        group_id = pick(detail, "group_id", "groupId")
    try:
        group_id = int(group_id) if group_id is not None else None
    except (TypeError, ValueError):
        group_id = None
    return (
        str(set_name) if set_name not in (None, "") else None,
        group_id,
    )


class TickermintProductsImporter(ApiImporter):
    """Searches TickerMint for each Limitless card and saves product identity."""

    name = "tickermint_products"
    api_base_url = API_BASE

    def api_probe_url(self) -> str:
        # Bare / returns 404. /products/search with a no-op query is the
        # cheapest documented endpoint and returns a small JSON envelope.
        return f"{API_BASE}/products/search?q=pikachu&game=pokemon"

    async def setup_schema(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(DDL)

    async def run(
        self,
        *,
        rematch: bool = False,
        concurrency: int = 4,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        await self.setup_schema()

        own_session = session is None
        if own_session:
            session = aiohttp.ClientSession(
                headers={"User-Agent": "DVS/0.1"}
            )

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT card_id, card_name, set_code, card_number
                    FROM card
                    ORDER BY card_id
                    """
                )
                cards = [
                    (r["card_id"], r["card_name"], r["set_code"], r["card_number"])
                    for r in rows
                ]

            self.logger.info(
                "%d card row(s) to consider (rematch=%s).", len(cards), rematch
            )
            if not cards:
                self.logger.info(
                    "Nothing to do. Populate the card table first "
                    "(e.g. dvs limitless --from-date ...)."
                )
                return

            sem = asyncio.Semaphore(concurrency)

            async def run(card: tuple) -> None:
                async with sem:
                    await self._match_card(session, card, rematch)

            await asyncio.gather(
                *(run(c) for c in cards), return_exceptions=True
            )
        finally:
            if own_session:
                await session.close()

    async def _match_card(
        self,
        session: aiohttp.ClientSession,
        card: tuple,
        rematch: bool,
    ) -> None:
        card_id, card_name, set_code, card_number = card

        log = self.logger
        log.debug(
            "_match_card start: card_id=%d name=%r set=%r number=%r rematch=%s",
            card_id, card_name, set_code, card_number, rematch,
        )

        async with self.pool.acquire() as conn:
            if not rematch:
                existing = await conn.fetchval(
                    "SELECT 1 FROM limitless_card_map WHERE limitless_card_id = $1",
                    card_id,
                )
                if existing:
                    log.debug(
                        "_match_card skip: card_id=%d already mapped", card_id
                    )
                    return

            # Cascading search: full query, then drop the collector
            # number, then keep only the name. Each step picks up where
            # the previous one ended (deduped by product_id), so nothing
            # is re-queried for no reason.
            queries: list[str] = []
            head = [card_name]
            if set_code:
                head.append(set_code)
            queries.append(" ".join(head + ([card_number] if card_number else [])))
            if card_number and set_code:
                queries.append(f"{card_name} {set_code}")
            elif card_number:
                queries.append(card_name)
            # Keep only the first occurrence of each query; the unique
            # list is also what we iterate when issuing GETs.
            seen: set[str] = set()
            ordered: list[str] = []
            for q in queries:
                if q and q not in seen:
                    seen.add(q)
                    ordered.append(q)
            log.debug(
                "_match_card cascade plan for card_id=%d: %d query pass(es) -> %s",
                card_id, len(ordered), ordered,
            )

            pool: dict[int, tuple[dict, str, int | None, str]] = {}
            for query in ordered:
                payload = await self.get_json(
                    session,
                    f"{API_BASE}/products/search",
                    params={"q": query, "game": "pokemon"},
                )
                candidates = to_results(payload)
                kept = 0
                for candidate, kind, similarity in filter_candidates(
                    candidates, card_name, card_number, logger=self.logger
                ):
                    pid = get_product_id(candidate)
                    if pid is None or pid in pool:
                        log.debug(
                            "_match_card skip duplicate: card_id=%d "
                            "pid=%s already in pool",
                            card_id, pid,
                        )
                        continue
                    pool[pid] = (candidate, kind, similarity, query)
                    kept += 1
                log.debug(
                    "_match_card cascade pass card_id=%d q=%r -> %d raw "
                    "candidate(s), %d new mapping(s) after filter (pool=%d)",
                    card_id, query, len(candidates), kept, len(pool),
                )
                # Skip broader passes once we've locked in the precise
                # tier -- exact_number is unambiguous (name + number),
                # so the wider queries would just add extra API calls
                # and fuzzy noise.
                precise = any(
                    payload_kind == "exact_number"
                    for _, payload_kind, _, _ in pool.values()
                )
                if precise and query == ordered[0]:
                    log.debug(
                        "_match_card cascade stop after exact_number hit "
                        "for card_id=%d (pool=%d)",
                        card_id, len(pool),
                    )
                    break
                # Otherwise cap the broader-pass cycle to just one more
                # round (full -> name+set / -> name) so we don't pay a
                # third round-trip for name-only fallbacks.
                if query != ordered[0]:
                    break

            log.debug(
                "_match_card pool ready: card_id=%d unique_pid(s)=%d",
                card_id, len(pool),
            )

            async with conn.transaction():
                # Wipe this card's mapping rows first so the table stays
                # in lockstep with what TickerMint just returned -- stale
                # candidates from a previous run do not linger.
                await conn.execute(
                    "DELETE FROM limitless_card_map WHERE limitless_card_id = $1",
                    card_id,
                )
                log.debug(
                    "_match_card wiped old mappings for card_id=%d", card_id
                )
                kinds: list[str] = []
                for pid, (candidate, kind, similarity, query) in pool.items():
                    if pid is None:
                        log.debug(
                            "_match_card skip persist: pid missing on "
                            "candidate %r",
                            candidate,
                        )
                        continue
                    log.debug(
                        "_match_card persist start: card_id=%d pid=%s "
                        "kind=%s similarity=%s query=%r",
                        card_id, pid, kind, similarity, query,
                    )
                    # Reuse the search payload when it already exposes
                    # the fields card_product needs; avoids one
                    # /products/{pid} GET per candidate. Falls back to
                    # a detail fetch when critical fields are missing.
                    if _search_payload_sufficient(candidate):
                        detail = candidate
                    else:
                        detail = await self.get_json(
                            session, f"{API_BASE}/products/{pid}"
                        )
                    product_id = await self._save_product(conn, detail, pid)
                    await conn.execute(
                        """
                        INSERT INTO limitless_card_map (
                            limitless_card_id, product_id,
                            match_kind, similarity,
                            search_query, captured_at
                        ) VALUES ($1, $2, $3, $4, $5, now())
                        ON CONFLICT (limitless_card_id, product_id) DO NOTHING
                        """,
                        card_id,
                        product_id,
                        kind,
                        similarity,
                        query,
                    )
                    kinds.append(kind)

        if not kinds:
            self.logger.info(
                "%d: %s %s %s -> unmatched",
                card_id,
                card_name,
                set_code or "",
                card_number or "",
            )
            self.logger.debug(
                "_match_card end: card_id=%d 0 candidates after cascade "
                "(tried %d query pass(es))",
                card_id, len(ordered),
            )
            return

        tally: dict[str, int] = {}
        for kind in kinds:
            tally[kind] = tally.get(kind, 0) + 1
        summary = ", ".join(f"{n} {k}" for k, n in tally.items())
        self.logger.info(
            "%d: %s %s %s -> %d candidate(s) [%s]",
            card_id,
            card_name,
            set_code or "",
            card_number or "",
            len(kinds),
            summary,
        )
        for tier in ("fuzzy", "exact_name", "exact_number"):
            count = tally.get(tier, 0)
            if count:
                self.logger.info(
                    "%d: %d %s candidate(s) need a quick eyeball before "
                    "trusting them -- see similarity column.",
                    card_id, count, tier,
                )
        self.logger.debug(
            "_match_card end: card_id=%d %d mapping(s) across %d query "
            "pass(es); breakdown=%s",
            card_id, len(kinds), len(ordered), tally,
        )

    async def _save_product(self, conn, detail: dict, fallback_product_id: int) -> int:
        product_id = get_product_id(detail) or fallback_product_id
        set_name, group_id = set_fields(detail)
        card_name = str(
            pick(detail, "name", "card_name", "product_name", "title")
            or product_id
        )
        collector_number = pick(
            detail,
            "number",
            "collector_number",
            "collectorNumber",
            "card_number",
        )
        rarity = pick(detail, "rarity")
        image_url = pick(detail, "image", "image_url", "imageUrl")
        source_url = pick(
            detail,
            "url",
            "source_url",
            "sourceUrl",
            "page_url",
            "pageUrl",
        )

        await conn.execute(
            """
            INSERT INTO card_product (
                product_id, card_name, set_name, collector_number,
                rarity, image_url, source_url, group_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (product_id) DO UPDATE
            SET card_name = EXCLUDED.card_name,
                set_name = EXCLUDED.set_name,
                collector_number = EXCLUDED.collector_number,
                rarity = EXCLUDED.rarity,
                image_url = EXCLUDED.image_url,
                source_url = EXCLUDED.source_url,
                group_id = EXCLUDED.group_id
            """,
            product_id,
            card_name,
            set_name,
            str(collector_number) if collector_number is not None else None,
            str(rarity) if rarity is not None else None,
            str(image_url) if image_url is not None else None,
            str(source_url) if source_url is not None else None,
            group_id,
        )
        return product_id


__all__ = ["TickermintProductsImporter"]