-- 01_load_dimensions.sql
-- Loads the three conformed Reporting dimensions from Core.
-- Surrogate keys are generated once and preserved by upserts on the Core natural IDs.

BEGIN;

INSERT INTO reporting.dim_date_reporting (
    date_id, full_date, week_day, month_day, month, year
)
SELECT
    date_id,
    full_date,
    extract(isodow FROM full_date)::smallint AS week_day,
    extract(day FROM full_date)::smallint AS month_day,
    month,
    year
FROM core.dim_date
ON CONFLICT (date_id) DO UPDATE
SET full_date = EXCLUDED.full_date,
    week_day   = EXCLUDED.week_day,
    month_day  = EXCLUDED.month_day,
    month     = EXCLUDED.month,
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

INSERT INTO reporting.dim_card_reporting (
    card_id, card_name, rarity
)
SELECT
    card_id,
    card_name,
    rarity
FROM core.dim_card
ON CONFLICT (card_id) DO UPDATE
SET card_name = EXCLUDED.card_name,
    rarity    = EXCLUDED.rarity;

COMMIT;
