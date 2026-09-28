-- 06_validate_core.sql
-- Validation and coverage report after loading Core.

-- ---------- Row counts ----------
SELECT 'dim_date' AS table_name, count(*) AS rows FROM core.dim_date
UNION ALL SELECT 'dim_pokemon', count(*) FROM core.dim_pokemon
UNION ALL SELECT 'dim_card', count(*) FROM core.dim_card
UNION ALL SELECT 'core_deck_result', count(*) FROM core.core_deck_result
UNION ALL SELECT 'core_card_price', count(*) FROM core.core_card_price
UNION ALL SELECT 'topic_base_stats_vs_competitive', count(*) FROM core.topic_base_stats_vs_competitive
UNION ALL SELECT 'topic_card_competitive', count(*) FROM core.topic_card_competitive
UNION ALL SELECT 'topic_pokemon_price', count(*) FROM core.topic_pokemon_price
ORDER BY table_name;

-- ---------- Integration coverage ----------
SELECT
    count(*) AS total_limitless_cards,
    count(u.card_id) AS cards_with_unique_tickermint_product,
    round(100.0 * count(u.card_id) / nullif(count(*), 0), 2) AS tickermint_match_pct
FROM core.dim_card c
LEFT JOIN core.v_card_product_unique u ON u.card_id = c.card_id;

SELECT
    count(*) AS total_limitless_cards,
    count(*) FILTER (WHERE EXISTS (
        SELECT 1 FROM core.card_pokemon_map m WHERE m.card_id = c.card_id
    )) AS cards_with_pokemon_mapping,
    round(
        100.0 * count(*) FILTER (WHERE EXISTS (
            SELECT 1 FROM core.card_pokemon_map m WHERE m.card_id = c.card_id
        )) / nullif(count(*), 0),
        2
    ) AS pokemon_mapping_pct
FROM core.dim_card c;

-- ---------- Unmapped cards ----------
SELECT *
FROM core.v_unmapped_cards
ORDER BY card_name, card_id;

-- ---------- Cards used competitively but not mapped to a Pokemon ----------
SELECT
    c.card_id,
    c.card_name,
    count(DISTINCT dc.deck_id) AS decks_using_card
FROM staging.deck_card dc
JOIN core.dim_card c ON c.card_id = dc.card_id
LEFT JOIN core.card_pokemon_map m ON m.card_id = dc.card_id
WHERE m.card_id IS NULL
GROUP BY c.card_id, c.card_name
ORDER BY decks_using_card DESC, c.card_name;

-- ---------- Cards with competitive usage but no loaded price history ----------
SELECT
    c.card_id,
    c.card_name,
    count(DISTINCT tc.deck_id) AS decks_using_card
FROM core.topic_card_competitive tc
JOIN core.dim_card c ON c.card_id = tc.card_id
LEFT JOIN core.core_card_price cp ON cp.card_id = tc.card_id
WHERE cp.card_id IS NULL
GROUP BY c.card_id, c.card_name
ORDER BY decks_using_card DESC, c.card_name;

-- ---------- Date ranges ----------
SELECT
    min(full_date) AS first_date,
    max(full_date) AS last_date,
    count(*) AS calendar_days
FROM core.dim_date;

SELECT
    min(d.full_date) AS first_competitive_date,
    max(d.full_date) AS last_competitive_date
FROM core.core_deck_result r
JOIN core.dim_date d ON d.date_id = r.date_id;

SELECT
    min(d.full_date) AS first_price_date,
    max(d.full_date) AS last_price_date
FROM core.core_card_price p
JOIN core.dim_date d ON d.date_id = p.date_id;

-- ---------- Type-order warning ----------
-- Since staging has no type slot, type_one/type_two are only deterministically sorted labels.
SELECT pokemon_id, pokemon_name, type_one, type_two
FROM core.dim_pokemon
WHERE type_two IS NOT NULL
ORDER BY pokemon_name
LIMIT 25;
