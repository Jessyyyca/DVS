-- 03_manual_card_pokemon_mapping_template.sql
-- OPTIONAL / AS NEEDED.
-- Run 02_load_dimensions_and_mapping.sql first, review core.v_unmapped_cards,
-- then add manual mappings for relevant Pokemon cards that cannot be matched automatically.
--
-- The mapping supports multi-Pokemon cards by inserting multiple rows for the same card_id.

-- Example pattern (replace IDs with your real values):
-- INSERT INTO core.card_pokemon_map (card_id, pokemon_id, match_method, note)
-- VALUES
--     (12345, 6, 'MANUAL', 'Radiant Charizard -> Charizard'),
--     (67890, 150, 'MANUAL', 'Mewtwo & Mew-GX -> Mewtwo'),
--     (67890, 151, 'MANUAL', 'Mewtwo & Mew-GX -> Mew')
-- ON CONFLICT (card_id, pokemon_id) DO UPDATE
-- SET match_method = 'MANUAL',
--     note = EXCLUDED.note;

-- Helpful lookup queries:
SELECT * FROM core.v_unmapped_cards ORDER BY card_name, card_id;

-- Search Pokemon IDs by name:
-- SELECT pokemon_id, pokemon_name
-- FROM core.dim_pokemon
-- WHERE lower(pokemon_name) LIKE '%charizard%';
