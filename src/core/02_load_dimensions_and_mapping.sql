BEGIN;

-- DIM_DATE: all dates between earliest and latest deck/price observation.
WITH bounds AS (
    SELECT min(d) AS min_date, max(d) AS max_date
    FROM (
        SELECT coalesce(play_date, event_date) AS d FROM public.deck
        UNION ALL
        SELECT price_date AS d FROM public.daily_price
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
    FROM public.pokemon_type pt
    JOIN public.type t ON t.url_id = pt.type_url
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
FROM public.pokemon p
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
FROM public.card c
LEFT JOIN public.card_product cp ON cp.card_id = c.card_id
ON CONFLICT (card_id) DO UPDATE SET
    card_name = excluded.card_name,
    rarity = excluded.rarity;

-- Conservative automatic Card -> Pokemon matching.
-- Only strips common suffixes at the END of a card name.
WITH card_norm AS (
    SELECT c.card_id,
           lower(trim(regexp_replace(
               regexp_replace(c.card_name, '[^[:alnum:] .-]', '', 'g'),
               '\\s+(ex|gx|v|vmax|vstar|break|prime|lv[.]?x)$', '', 'i'
           ))) AS normalized_name
    FROM core.dim_card c
), candidates AS (
    SELECT cn.card_id, p.pokemon_id,
           count(*) OVER (PARTITION BY cn.card_id) AS candidate_count
    FROM card_norm cn
    JOIN core.dim_pokemon p
      ON lower(p.pokemon_name) = cn.normalized_name
)
INSERT INTO core.card_pokemon_map(card_id, pokemon_id, match_method)
SELECT card_id, pokemon_id, 'automatic'
FROM candidates
WHERE candidate_count = 1
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
