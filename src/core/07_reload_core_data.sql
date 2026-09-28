-- Destructive data refresh for Core while preserving structure and manual mappings.
-- Run 02, 04, 05, and 06 afterwards.

BEGIN;

TRUNCATE TABLE
    core.topic_base_stats_vs_competitive,
    core.topic_card_competitive,
    core.topic_pokemon_price,
    core.core_card_price,
    core.core_deck_result;

-- Keep manually reviewed mappings, remove only automatic ones so they can be regenerated.
DELETE FROM core.card_pokemon_map
WHERE match_method = 'automatic';

-- Dimensions are reloaded/upserted by 02_load_dimensions_and_mapping.sql.

COMMIT;
