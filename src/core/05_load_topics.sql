BEGIN;

-- Topic 1: one deck x Pokemon. If several cards in one deck map to the same
-- Pokemon, their quantities are summed.
INSERT INTO core.topic_base_stats_vs_competitive(deck_id, pokemon_id, pokemon_copy_count)
SELECT dc.deck_id,
       m.pokemon_id,
       sum(dc.quantity)::int AS pokemon_copy_count
FROM staging.deck_card dc
JOIN core.core_deck_result dr ON dr.deck_id = dc.deck_id
JOIN core.card_pokemon_map m ON m.card_id = dc.card_id
GROUP BY dc.deck_id, m.pokemon_id
ON CONFLICT (deck_id, pokemon_id) DO UPDATE SET
    pokemon_copy_count = excluded.pokemon_copy_count;

-- Topic 2: one deck x card.
INSERT INTO core.topic_card_competitive(deck_id, card_id, card_copy_count)
SELECT dc.deck_id,
       dc.card_id,
       sum(dc.quantity)::int AS card_copy_count
FROM staging.deck_card dc
JOIN core.core_deck_result dr ON dr.deck_id = dc.deck_id
JOIN core.dim_card c ON c.card_id = dc.card_id
GROUP BY dc.deck_id, dc.card_id
ON CONFLICT (deck_id, card_id) DO UPDATE SET
    card_copy_count = excluded.card_copy_count;

-- Topic 3: integration relationship Pokemon x card. Price observations remain
-- in CORE_CARD_PRICE and are reached through card_id.
INSERT INTO core.topic_pokemon_price(pokemon_id, card_id)
SELECT DISTINCT m.pokemon_id, m.card_id
FROM core.card_pokemon_map m
JOIN core.core_card_price p ON p.card_id = m.card_id
ON CONFLICT (pokemon_id, card_id) DO NOTHING;

COMMIT;
