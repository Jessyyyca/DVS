-- Add reviewed mappings here. Keep this file as a template and only insert
-- mappings your group has explicitly verified.
--
-- Example:
-- INSERT INTO core.card_pokemon_map(card_id, pokemon_id, match_method)
-- VALUES (123, 6, 'manual')
-- ON CONFLICT (card_id, pokemon_id) DO UPDATE
-- SET match_method = 'manual';
--
-- A card may map to more than one Pokemon if your analytical rule requires it
-- (e.g. a multi-Pokemon card). Such a choice should be documented because the
-- same card quantity will then contribute to each mapped Pokemon in Topic 1.

SELECT * FROM core.v_unmapped_cards;
