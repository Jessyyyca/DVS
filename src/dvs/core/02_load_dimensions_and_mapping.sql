-- 02_load_dimensions_and_mapping.sql
-- Loads DIM_DATE, DIM_POKEMON, DIM_CARD and rebuilds automatic Card -> Pokemon mappings.

BEGIN;

-- ---------- DIM_DATE ----------
-- Create a continuous calendar from the earliest to latest relevant source date.
WITH source_dates AS (
    SELECT coalesce(play_date::date, event_date::date) AS d
    FROM staging.deck
    WHERE coalesce(play_date::date, event_date::date) IS NOT NULL

    UNION ALL

    SELECT price_date::date AS d
    FROM staging.daily_price
    WHERE price_date IS NOT NULL
),
bounds AS (
    SELECT min(d) AS min_date, max(d) AS max_date
    FROM source_dates
),
calendar AS (
    SELECT gs::date AS full_date
    FROM bounds b
    CROSS JOIN LATERAL generate_series(b.min_date, b.max_date, interval '1 day') gs
    WHERE b.min_date IS NOT NULL AND b.max_date IS NOT NULL
)
INSERT INTO core.dim_date (date_id, full_date, day, month, quarter, year)
SELECT
    to_char(full_date, 'YYYYMMDD')::integer AS date_id,
    full_date,
    extract(day FROM full_date)::smallint,
    extract(month FROM full_date)::smallint,
    extract(quarter FROM full_date)::smallint,
    extract(year FROM full_date)::integer
FROM calendar
ON CONFLICT (date_id) DO UPDATE
SET full_date = EXCLUDED.full_date,
    day       = EXCLUDED.day,
    month     = EXCLUDED.month,
    quarter   = EXCLUDED.quarter,
    year      = EXCLUDED.year;

-- ---------- DIM_POKEMON ----------
-- IMPORTANT: staging.pokemon_type has no slot/order column.
-- Therefore type_one/type_two below are deterministic alphabetical positions ONLY;
-- they must NOT be interpreted as PokeAPI primary/secondary type.
WITH typed AS (
    SELECT
        pt.pokemon_id,
        t.name AS type_name,
        row_number() OVER (
            PARTITION BY pt.pokemon_id
            ORDER BY lower(t.name), t.url_id
        ) AS rn
    FROM staging.pokemon_type pt
    JOIN staging.type t
      ON t.url_id = pt.type_url
),
type_pivot AS (
    SELECT
        pokemon_id,
        max(type_name) FILTER (WHERE rn = 1) AS type_one,
        max(type_name) FILTER (WHERE rn = 2) AS type_two
    FROM typed
    GROUP BY pokemon_id
)
INSERT INTO core.dim_pokemon (
    pokemon_id,
    pokemon_name,
    hp,
    attack,
    defense,
    special_attack,
    special_defense,
    speed,
    type_one,
    type_two
)
SELECT
    p.id,
    p.name,
    p.hp,
    p.attack,
    p.defense,
    p.special_attack,
    p.special_defense,
    p.speed,
    tp.type_one,
    tp.type_two
FROM staging.pokemon p
LEFT JOIN type_pivot tp
  ON tp.pokemon_id = p.id
ON CONFLICT (pokemon_id) DO UPDATE
SET pokemon_name    = EXCLUDED.pokemon_name,
    hp              = EXCLUDED.hp,
    attack          = EXCLUDED.attack,
    defense         = EXCLUDED.defense,
    special_attack  = EXCLUDED.special_attack,
    special_defense = EXCLUDED.special_defense,
    speed           = EXCLUDED.speed,
    type_one        = EXCLUDED.type_one,
    type_two        = EXCLUDED.type_two;

-- ---------- DIM_CARD ----------
-- Rarity is taken only from an unambiguous one-to-one Limitless <-> TickerMint product mapping.
-- Competitive cards are retained even if no TickerMint product could be resolved; rarity is then NULL.
INSERT INTO core.dim_card (card_id, card_name, rarity)
SELECT
    c.card_id,
    c.card_name,
    u.rarity
FROM staging.card c
LEFT JOIN core.v_card_product_unique u
  ON u.card_id = c.card_id
ON CONFLICT (card_id) DO UPDATE
SET card_name = EXCLUDED.card_name,
    rarity    = EXCLUDED.rarity;

-- ---------- Card -> Pokemon mapping ----------
-- Preserve manual mappings but refresh automatic exact-normalized mappings.
DELETE FROM core.card_pokemon_map
WHERE match_method = 'AUTO_NORMALIZED_NAME';

INSERT INTO core.card_pokemon_map (card_id, pokemon_id, match_method, note)
SELECT
    c.card_id,
    p.pokemon_id,
    'AUTO_NORMALIZED_NAME',
    'Exact match after conservative normalization of card and Pokemon names.'
FROM core.dim_card c
JOIN core.dim_pokemon p
  ON core.normalize_pokemon_name(c.card_name)
   = core.normalize_pokemon_name(p.pokemon_name)
WHERE core.normalize_pokemon_name(c.card_name) <> ''
ON CONFLICT (card_id, pokemon_id) DO NOTHING;

COMMIT;

-- Review cards that still need manual mapping:
SELECT * FROM core.v_unmapped_cards ORDER BY card_name, card_id;
