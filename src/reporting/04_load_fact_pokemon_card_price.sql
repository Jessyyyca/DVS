-- 04_load_fact_pokemon_card_price.sql
-- Star 3: Pokemon base stats vs card prices.
-- Grain: one Pokemon x one Card x one date.

BEGIN;

TRUNCATE TABLE reporting.fact_pokemon_card_price;

WITH price AS (
    SELECT
        card_id,
        date_id,
        avg(market_price)::numeric(14,4) AS market_price,
        min(market_price)::numeric(14,4) AS min_market_price,
        max(market_price)::numeric(14,4) AS max_market_price
    FROM core.core_card_price
    GROUP BY card_id, date_id
)
INSERT INTO reporting.fact_pokemon_card_price (
    pokemon_key,
    card_key,
    date_key,
    market_price,
    min_market_price,
    max_market_price
)
SELECT
    p.pokemon_key,
    c.card_key,
    d.date_key,
    pr.market_price,
    pr.min_market_price,
    pr.max_market_price
FROM core.topic_pokemon_price t
JOIN price pr
  ON pr.card_id = t.card_id
JOIN reporting.dim_pokemon_reporting p
  ON p.pokemon_id = t.pokemon_id
JOIN reporting.dim_card_reporting c
  ON c.card_id = t.card_id
JOIN reporting.dim_date_reporting d
  ON d.date_id = pr.date_id;

COMMIT;
