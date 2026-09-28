-- 01_staging_quality_checks.sql
-- Run before loading CORE. This script does not modify data.
-- Review especially the "ambiguous TickerMint mapping" and "conflicting price" result sets.

-- 1) Duplicate natural keys in source tables
SELECT 'duplicate staging.card.card_id' AS check_name, card_id, count(*) AS row_count
FROM staging.card
GROUP BY card_id
HAVING count(*) > 1;

SELECT 'duplicate staging.deck.deck_id' AS check_name, deck_id, count(*) AS row_count
FROM staging.deck
GROUP BY deck_id
HAVING count(*) > 1;

SELECT 'duplicate staging.pokemon.id' AS check_name, id, count(*) AS row_count
FROM staging.pokemon
GROUP BY id
HAVING count(*) > 1;

-- 2) Orphan rows
SELECT 'orphan deck_card -> deck' AS check_name, dc.deck_id, count(*) AS row_count
FROM staging.deck_card dc
LEFT JOIN staging.deck d ON d.deck_id = dc.deck_id
WHERE d.deck_id IS NULL
GROUP BY dc.deck_id;

SELECT 'orphan deck_card -> card' AS check_name, dc.card_id, count(*) AS row_count
FROM staging.deck_card dc
LEFT JOIN staging.card c ON c.card_id = dc.card_id
WHERE c.card_id IS NULL
GROUP BY dc.card_id;

SELECT 'orphan pokemon_type -> pokemon' AS check_name, pt.pokemon_id, count(*) AS row_count
FROM staging.pokemon_type pt
LEFT JOIN staging.pokemon p ON p.id = pt.pokemon_id
WHERE p.id IS NULL
GROUP BY pt.pokemon_id;

SELECT 'orphan pokemon_type -> type' AS check_name, pt.type_url, count(*) AS row_count
FROM staging.pokemon_type pt
LEFT JOIN staging.type t ON t.url_id = pt.type_url
WHERE t.url_id IS NULL
GROUP BY pt.type_url;

-- 3) Limitless card_id -> TickerMint product_id ambiguity
SELECT
    card_id,
    count(DISTINCT product_id) AS distinct_product_ids,
    string_agg(DISTINCT product_id::text, ', ' ORDER BY product_id::text) AS product_ids
FROM staging.card_product
WHERE card_id IS NOT NULL AND product_id IS NOT NULL
GROUP BY card_id
HAVING count(DISTINCT product_id) <> 1
ORDER BY distinct_product_ids DESC, card_id;

-- 4) Reverse ambiguity: one TickerMint product assigned to several Limitless cards
SELECT
    product_id,
    count(DISTINCT card_id) AS distinct_card_ids,
    string_agg(DISTINCT card_id::text, ', ' ORDER BY card_id::text) AS card_ids
FROM staging.card_product
WHERE card_id IS NOT NULL AND product_id IS NOT NULL
GROUP BY product_id
HAVING count(DISTINCT card_id) <> 1
ORDER BY distinct_card_ids DESC, product_id;

-- 5) Conflicting prices at the logical daily-price grain.
-- Identical duplicate rows are less serious; different market prices are a data-quality error.
SELECT
    product_id,
    printing_type,
    price_date,
    count(*) AS row_count,
    count(DISTINCT market_price) AS distinct_prices,
    min(market_price) AS min_price,
    max(market_price) AS max_price
FROM staging.daily_price
GROUP BY product_id, printing_type, price_date
HAVING count(DISTINCT market_price) > 1
ORDER BY price_date, product_id, printing_type;

-- 6) Missing dates needed for Core deck results
SELECT deck_id, play_date, event_date
FROM staging.deck
WHERE play_date IS NULL AND event_date IS NULL;

-- 7) Pokemon with more than two types (should normally be empty)
SELECT pokemon_id, count(*) AS type_count
FROM staging.pokemon_type
GROUP BY pokemon_id
HAVING count(*) > 2;
