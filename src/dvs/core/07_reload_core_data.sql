-- 07_reload_core_data.sql
-- Optional helper for a full DATA reload while keeping the Core schema and manual card->Pokemon mappings.
-- Run this before scripts 02, 04 and 05 if you want a clean reload.

BEGIN;

TRUNCATE TABLE
    core.topic_base_stats_vs_competitive,
    core.topic_card_competitive,
    core.topic_pokemon_price,
    core.core_card_price,
    core.core_deck_result,
    core.dim_date
RESTART IDENTITY;

-- DIM_CARD and DIM_POKEMON are updated/upserted by script 02 rather than truncated,
-- because core.card_pokemon_map has foreign keys to them and may contain manual mappings.

COMMIT;
