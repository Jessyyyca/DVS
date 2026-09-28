BEGIN;

-- DIM_DATE: all dates between earliest and latest deck/price observation.
WITH bounds AS (
    SELECT min(d) AS min_date, max(d) AS max_date
    FROM (
        SELECT coalesce(play_date, event_date) AS d FROM staging.deck
        UNION ALL
        SELECT price_date AS d FROM staging.daily_price
    ) x
    WHERE d IS NOT NULL
), dates AS (
    SELECT generate_series(min_date, max_date, interval '1 day')::date AS full_date
    FROM bounds
    WHERE min_date IS NOT NULL AND max_date IS NOT NULL
)
INSERT INTO core.dim_date(date_id, full_date, day, month, quarter, year)
SELECT to_char(full_date,'YYYYMMDD')::int,
       full_date,
       extract(day from full_date)::int,
       extract(month from full_date)::int,
       extract(quarter from full_date)::int,
       extract(year from full_date)::int
FROM dates
ON CONFLICT (date_id) DO UPDATE SET
    full_date = excluded.full_date,
    day = excluded.day,
    month = excluded.month,
    quarter = excluded.quarter,
    year = excluded.year;

-- DIM_POKEMON. Because staging does not store PokeAPI type slot, types are
-- ordered alphabetically to keep the load deterministic.
WITH type_rows AS (
    SELECT pt.pokemon_id,
           t.name AS type_name,
           row_number() OVER (PARTITION BY pt.pokemon_id ORDER BY t.name) AS rn
    FROM staging.pokemon_type pt
    JOIN staging.type t ON t.url_id = pt.type_url
), type_pivot AS (
    SELECT pokemon_id,
           max(type_name) FILTER (WHERE rn = 1) AS type_one,
           max(type_name) FILTER (WHERE rn = 2) AS type_two
    FROM type_rows
    GROUP BY pokemon_id
)
INSERT INTO core.dim_pokemon(
    pokemon_id, pokemon_name, hp, attack, defense,
    special_attack, special_defense, speed, type_one, type_two
)
SELECT p.id, p.name, p.hp, p.attack, p.defense,
       p.special_attack, p.special_defense, p.speed,
       tp.type_one, tp.type_two
FROM staging.pokemon p
LEFT JOIN type_pivot tp ON tp.pokemon_id = p.id
ON CONFLICT (pokemon_id) DO UPDATE SET
    pokemon_name = excluded.pokemon_name,
    hp = excluded.hp,
    attack = excluded.attack,
    defense = excluded.defense,
    special_attack = excluded.special_attack,
    special_defense = excluded.special_defense,
    speed = excluded.speed,
    type_one = excluded.type_one,
    type_two = excluded.type_two;

-- DIM_CARD. Limitless is the canonical card identity, TickerMint contributes rarity.
INSERT INTO core.dim_card(card_id, card_name, rarity)
SELECT c.card_id, c.card_name, cp.rarity
FROM staging.card c
LEFT JOIN staging.card_product cp ON cp.card_id = c.card_id
ON CONFLICT (card_id) DO UPDATE SET
    card_name = excluded.card_name,
    rarity = excluded.rarity;

-- Conservative automatic Card -> Pokemon matching.
-- Normalization rules (applied left to right; everything case-insensitive):
--   1. Owner prefixes "X's" / "X's " are removed (N's Vanillite -> Vanillite,
--      Cynthia's Gible -> Gible, Team Rocket's Moltres ex -> Moltres,
--      Steven's Baltoy -> Baltoy).
--   2. Trainer-only owner prefixes without an apostrophe are removed
--      (Cheren, Friends in Paldea, Levincia, etc. still fall through because
--      the result is not a Pokemon name -- that's intentional).
--   3. "Mega " is stripped from the front (Mega Gengar ex -> Gengar).
--      PokeAPI does not have a base "Mega X" species; the Mega form is
--      stored separately and intentionally not auto-linked.
--   4. Common TCG suffixes are stripped from the END (ex, GX, V, VMAX,
--      VSTAR, BREAK, PRIME, LV.X, etc.). Multiple suffixes can stack.
--   5. Regional prefixes (Hisuian, Galarian, Alolan, Paldean) are stripped
--      only when the remaining token matches a known Pokemon in dim_pokemon.
--      Otherwise the regional prefix is preserved so the card remains unmapped
--      rather than being silently aliased to the base form.
--   6. All non-alphanumeric characters are collapsed to a single space, then
--      trimmed. Apostrophes are kept as spaces, not deleted (otherwise
--      "N's" would become "ns" and miss the owner-prefix rule).
WITH cleaned AS (
    SELECT
        c.card_id,
        lower(c.card_name) AS raw_name
    FROM core.dim_card c
), step_owner AS (
    -- Drop "<Word>'s" at the start, where <Word> is 1-20 letters/digits.
    -- Optional single space is consumed too.
    SELECT card_id,
           regexp_replace(
               raw_name,
               '^\s*[a-z0-9]{1,20}\x27\s*\s*',
               '',
               'i'
           ) AS name
    FROM cleaned
), step_mega AS (
    -- "Mega " prefix (case-insensitive).
    SELECT card_id,
           regexp_replace(name, '^mega\s+', '', 'i') AS name
    FROM step_owner
), step_suffix AS (
    -- Strip a trailing TCG suffix token. The pattern combines every variant
    -- into a single alternation; alternation tries alternatives left-to-right
    -- and picks the first match, so longer / more specific tokens MUST come
    -- first (otherwise "v" in "vmax" would be eaten as bare-V, and "promo"
    -- in "prerelease promo" would be eaten before the longer match).
    -- Regex legend (note the Unicode star glyph is matched as its three-byte UTF-8 literal):
    --   Multi-word suffixes : prerelease promo, staff promo, league promo,
    --                         prelease promo, tag team, delta species,
    --                         spirit link, prism star, v-union, v-double
    --   Single-word TCG     : radiant, legend, spiral, vstar, vmax, gx,
    --                         break, prime, baby, ex
    --   Bare single letter  : v, m
    --   Old-style level     : lv.x / lv.x / lvx
    --   Generic fallbacks   : promo, star, legend, star-glyph
    SELECT card_id,
           regexp_replace(name,
               '\s+('
               || 'prerelease promo|staff promo|league promo|prelease promo'
               || '|tag team|delta species|spirit link|prism star'
               || '|v-union|v-double'
               || '|radiant|legend|spiral|vstar|vmax|gx|break|prime|baby'
               || '|ex'
               || '|lv\.?x'
               || '|promo|legend|star'
               || '|\xE2\x98\x85'
               || '|v|m'
               || ')\s*$',
               '',
               'i'
           ) AS name
    FROM step_mega
), step_alphanum AS (
    -- Collapse every non-alphanumeric run to a single space, then trim.
    -- Spaces (not deletions) keep owner-prefix / Mega-prefix boundaries visible.
    SELECT card_id,
           trim(regexp_replace(name, '[^a-z0-9]+', ' ', 'g')) AS name
    FROM step_suffix
), candidates AS (
    -- First try the name as-is (catches base, Mega-stripped, owner-stripped cards).
    SELECT cn.card_id, p.pokemon_id
    FROM step_alphanum cn
    JOIN core.dim_pokemon p
      ON lower(p.pokemon_name) = cn.name
    UNION ALL
    -- Then try again after stripping a leading regional prefix. Only succeeds
    -- when the remainder is itself a real Pokemon (e.g. "Hisuian Typhlosion" ->
    -- "Typhlosion"). "Hisuian Pokémon-That-Does-Not-Exist" stays unmapped.
    SELECT cn.card_id, p.pokemon_id
    FROM step_alphanum cn
    JOIN core.dim_pokemon p
      ON lower(p.pokemon_name) = regexp_replace(
             cn.name,
             '^(hisuian|galarian|alolan|paldean|unovan|kalosian|original)\s+',
             '',
             'i'
         )
), ranked AS (
    SELECT card_id,
           pokemon_id,
           count(*) OVER (PARTITION BY card_id) AS candidate_count
    FROM candidates
)
INSERT INTO core.card_pokemon_map(card_id, pokemon_id, match_method)
SELECT card_id, pokemon_id, 'automatic'
FROM ranked
WHERE candidate_count = 1
ON CONFLICT (card_id, pokemon_id) DO NOTHING;

-- Fuzzy fallback: cards the exact-normalized pass could not resolve (e.g.
-- regional forms like "Hisuian Typhlosion" or alternate forms not covered
-- by the suffix regex) are linked to the Pokemon with the highest
-- similarity() score. The threshold keeps trainer / energy / item cards
-- out of the mapping because their names rarely share trigrams with any
-- Pokemon. Re-runnable: rows tagged 'automatic_fuzzy' are inserted only
-- for cards that have no mapping yet.
WITH unmatched AS (
    SELECT c.card_id, c.card_name
    FROM core.dim_card c
    WHERE NOT EXISTS (
        SELECT 1 FROM core.card_pokemon_map m WHERE m.card_id = c.card_id
    )
), scored AS (
    SELECT u.card_id,
           p.pokemon_id,
           similarity(u.card_name, p.pokemon_name) AS sim
    FROM unmatched u
    CROSS JOIN core.dim_pokemon p
), best AS (
    SELECT DISTINCT ON (card_id)
        card_id,
        pokemon_id,
        sim
    FROM scored
    WHERE sim >= 0.6
    ORDER BY card_id, sim DESC, pokemon_id
)
INSERT INTO core.card_pokemon_map(card_id, pokemon_id, match_method)
SELECT card_id, pokemon_id, 'automatic_fuzzy'
FROM best
ON CONFLICT (card_id, pokemon_id) DO NOTHING;

COMMIT;

-- Review cards that still need manual integration decisions.
CREATE OR REPLACE VIEW core.v_unmapped_cards AS
SELECT c.card_id, c.card_name, c.rarity
FROM core.dim_card c
WHERE NOT EXISTS (
    SELECT 1 FROM core.card_pokemon_map m WHERE m.card_id = c.card_id
)
ORDER BY c.card_name, c.card_id;
