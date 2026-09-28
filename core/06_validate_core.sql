-- Core validation / handover checks.

SELECT 'dim_date' AS table_name, count(*) AS rows FROM core.dim_date
UNION ALL SELECT 'dim_pokemon', count(*) FROM core.dim_pokemon
UNION ALL SELECT 'dim_card', count(*) FROM core.dim_card
UNION ALL SELECT 'core_deck_result', count(*) FROM core.core_deck_result
UNION ALL SELECT 'core_card_price', count(*) FROM core.core_card_price
UNION ALL SELECT 'topic_base_stats_vs_competitive', count(*) FROM core.topic_base_stats_vs_competitive
UNION ALL SELECT 'topic_card_competitive', count(*) FROM core.topic_card_competitive
UNION ALL SELECT 'topic_pokemon_price', count(*) FROM core.topic_pokemon_price
ORDER BY table_name;

-- Mapping coverage.
SELECT
    count(*) AS total_cards,
    count(*) FILTER (WHERE EXISTS (
        SELECT 1 FROM core.card_pokemon_map m WHERE m.card_id = c.card_id
    )) AS mapped_cards,
    count(*) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM core.card_pokemon_map m WHERE m.card_id = c.card_id
    )) AS unmapped_cards
FROM core.dim_card c;

-- Automatic vs manual mappings.
SELECT match_method, count(*)
FROM core.card_pokemon_map
GROUP BY match_method
ORDER BY match_method;

-- Core date ranges.
SELECT min(d.full_date) AS first_deck_date, max(d.full_date) AS last_deck_date
FROM core.core_deck_result r
JOIN core.dim_date d ON d.date_id = r.date_id;

SELECT min(d.full_date) AS first_price_date, max(d.full_date) AS last_price_date
FROM core.core_card_price p
JOIN core.dim_date d ON d.date_id = p.date_id;

-- Cards with no Core price history.
SELECT c.card_id, c.card_name
FROM core.dim_card c
WHERE NOT EXISTS (
    SELECT 1 FROM core.core_card_price p WHERE p.card_id = c.card_id
)
ORDER BY c.card_name;

-- Cards used competitively but not mapped to a Pokemon.
SELECT DISTINCT c.card_id, c.card_name
FROM core.topic_card_competitive tc
JOIN core.dim_card c ON c.card_id = tc.card_id
WHERE NOT EXISTS (
    SELECT 1 FROM core.card_pokemon_map m WHERE m.card_id = c.card_id
)
ORDER BY c.card_name;

-- Sanity: no topic rows should refer to missing support rows because FKs enforce this.
SELECT count(*) AS negative_deck_results
FROM core.core_deck_result
WHERE wins < 0 OR losses < 0 OR ties < 0;

SELECT count(*) AS nonpositive_topic_quantities
FROM (
    SELECT pokemon_copy_count AS qty FROM core.topic_base_stats_vs_competitive
    UNION ALL
    SELECT card_copy_count FROM core.topic_card_competitive
) q
WHERE qty <= 0;
