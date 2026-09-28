-- 06_validate_reporting.sql
-- Basic Reporting-layer quality checks.

-- Row counts.
SELECT 'dim_date_reporting' AS object_name, count(*) AS row_count
FROM reporting.dim_date_reporting
UNION ALL
SELECT 'dim_pokemon_reporting', count(*) FROM reporting.dim_pokemon_reporting
UNION ALL
SELECT 'dim_card_reporting', count(*) FROM reporting.dim_card_reporting
UNION ALL
SELECT 'fact_pokemon_competitive', count(*) FROM reporting.fact_pokemon_competitive
UNION ALL
SELECT 'fact_card_competitive_price', count(*) FROM reporting.fact_card_competitive_price
UNION ALL
SELECT 'fact_pokemon_card_price', count(*) FROM reporting.fact_pokemon_card_price;

-- Grain checks: all should return zero rows.
SELECT pokemon_key, date_key, count(*)
FROM reporting.fact_pokemon_competitive
GROUP BY pokemon_key, date_key
HAVING count(*) > 1;

SELECT card_key, date_key, count(*)
FROM reporting.fact_card_competitive_price
GROUP BY card_key, date_key
HAVING count(*) > 1;

SELECT pokemon_key, card_key, date_key, count(*)
FROM reporting.fact_pokemon_card_price
GROUP BY pokemon_key, card_key, date_key
HAVING count(*) > 1;

-- Usage denominators must not be smaller than the corresponding numerator.
SELECT *
FROM reporting.fact_pokemon_competitive
WHERE decks_using_pokemon > total_decks;

SELECT *
FROM reporting.fact_card_competitive_price
WHERE decks_using_card > total_decks;

-- Average price must lie between min and max whenever all three are present.
SELECT *
FROM reporting.fact_card_competitive_price
WHERE market_price IS NOT NULL
  AND (market_price < min_market_price OR market_price > max_market_price);

SELECT *
FROM reporting.fact_pokemon_card_price
WHERE market_price < min_market_price
   OR market_price > max_market_price;

-- Dimension coverage against Core.
SELECT
    (SELECT count(*) FROM core.dim_date) AS core_dates,
    (SELECT count(*) FROM reporting.dim_date_reporting) AS reporting_dates,
    (SELECT count(*) FROM core.dim_pokemon) AS core_pokemon,
    (SELECT count(*) FROM reporting.dim_pokemon_reporting) AS reporting_pokemon,
    (SELECT count(*) FROM core.dim_card) AS core_cards,
    (SELECT count(*) FROM reporting.dim_card_reporting) AS reporting_cards;
