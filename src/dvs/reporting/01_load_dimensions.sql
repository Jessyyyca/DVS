-- 01_load_dimensions.sql
-- Loads the three conformed Reporting dimensions from Core.
-- Surrogate keys are generated once and preserved by upserts on the Core natural IDs.

BEGIN;

INSERT INTO reporting.dim_date_reporting (
    date_id, full_date, weekday, monthday, month, quarter, year
)
SELECT
    date_id,
    full_date,
    extract(isodow FROM full_date)::smallint AS weekday,
    extract(day FROM full_date)::smallint AS monthday,
    month,
    quarter,
    year
FROM core.dim_date
ON CONFLICT (date_id) DO UPDATE
SET full_date = EXCLUDED.full_date,
    weekday   = EXCLUDED.weekday,
    monthday  = EXCLUDED.monthday,
    month     = EXCLUDED.month,
    quarter   = EXCLUDED.quarter,
    year      = EXCLUDED.year;

INSERT INTO reporting.dim_pokemon_reporting (
    pokemon_id, pokemon_name, hp, attack, defense,
    special_attack, special_defense, speed, type_one, type_two
)
SELECT
    pokemon_id, pokemon_name, hp, attack, defense,
    special_attack, special_defense, speed, type_one, type_two
FROM core.dim_pokemon
ON CONFLICT (pokemon_id) DO UPDATE
SET pokemon_name     = EXCLUDED.pokemon_name,
    hp               = EXCLUDED.hp,
    attack           = EXCLUDED.attack,
    defense          = EXCLUDED.defense,
    special_attack   = EXCLUDED.special_attack,
    special_defense  = EXCLUDED.special_defense,
    speed            = EXCLUDED.speed,
    type_one         = EXCLUDED.type_one,
    type_two         = EXCLUDED.type_two;

-- Star_Schemas_Reporting.md contains set_name, but the current Core DIM_CARD
-- does not contain a set attribute. Reporting therefore leaves set_name NULL
-- instead of bypassing Core and reading the source/staging layer directly.
INSERT INTO reporting.dim_card_reporting (
    card_id, card_name, set_name, rarity
)
SELECT
    card_id,
    card_name,
    NULL::text AS set_name,
    rarity
FROM core.dim_card
ON CONFLICT (card_id) DO UPDATE
SET card_name = EXCLUDED.card_name,
    rarity    = EXCLUDED.rarity;

COMMIT;
