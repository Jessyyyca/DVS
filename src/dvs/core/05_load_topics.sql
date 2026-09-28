-- 05_load_topics.sql
-- Populates the three analysis topic tables from the integrated Core data.
-- Safe to rerun: topic tables are rebuilt from current source/core data.

BEGIN;

TRUNCATE TABLE
    core.topic_base_stats_vs_competitive,
    core.topic_card_competitive,
    core.topic_pokemon_price;

-- ---------- Topic 1: Base stats vs competitive ----------
-- Grain: one Deck x one Pokemon.
-- If multiple cards in the same deck map to the same Pokemon, their quantities are summed.
-- If a multi-Pokemon card has multiple manual mappings, its quantity contributes to each mapped Pokemon.
INSERT INTO core.topic_base_stats_vs_competitive (
    deck_id,
    pokemon_id,
    pokemon_copy_count
)
SELECT
    dc.deck_id,
    m.pokemon_id,
    sum(dc.quantity)::integer AS pokemon_copy_count
FROM staging.deck_card dc
JOIN core.core_deck_result dr
  ON dr.deck_id = dc.deck_id
JOIN core.dim_card c
  ON c.card_id = dc.card_id
JOIN core.card_pokemon_map m
  ON m.card_id = dc.card_id
WHERE dc.quantity IS NOT NULL
  AND dc.quantity > 0
GROUP BY dc.deck_id, m.pokemon_id;

-- ---------- Topic 2: Card competitive ----------
-- Grain: one Deck x one Card.
INSERT INTO core.topic_card_competitive (
    deck_id,
    card_id,
    card_copy_count
)
SELECT
    dc.deck_id,
    dc.card_id,
    sum(dc.quantity)::integer AS card_copy_count
FROM staging.deck_card dc
JOIN core.core_deck_result dr
  ON dr.deck_id = dc.deck_id
JOIN core.dim_card c
  ON c.card_id = dc.card_id
WHERE dc.quantity IS NOT NULL
  AND dc.quantity > 0
GROUP BY dc.deck_id, dc.card_id;

-- ---------- Topic 3: Pokemon vs price ----------
-- Grain: one Pokemon x one Card.
-- Price observations themselves stay in CORE_CARD_PRICE and are joined by card_id in Reporting.
INSERT INTO core.topic_pokemon_price (pokemon_id, card_id)
SELECT DISTINCT
    m.pokemon_id,
    m.card_id
FROM core.card_pokemon_map m
JOIN core.dim_pokemon p
  ON p.pokemon_id = m.pokemon_id
JOIN core.dim_card c
  ON c.card_id = m.card_id;

COMMIT;
