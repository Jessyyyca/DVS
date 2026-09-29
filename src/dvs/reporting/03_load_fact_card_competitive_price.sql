-- 03_load_fact_card_competitive_price.sql
-- Analysis scenario 2: Card price vs competitive performance.
-- Grain: one Card x one date.
-- A fact row is created when either competitive usage OR a price observation exists.
-- This means daily price history remains present even on dates without tournaments.

BEGIN;

TRUNCATE TABLE reporting.fact_card_competitive_price;

WITH total_decks_per_date AS (
    SELECT
        date_id,
        count(DISTINCT deck_id)::bigint AS total_decks
    FROM core.core_deck_result
    GROUP BY date_id
),
competitive AS (
    SELECT
        t.card_id,
        dr.date_id,
        count(DISTINCT t.deck_id)::bigint AS decks_using_card,
        sum(t.card_copy_count)::bigint AS card_copy_count,
        sum(dr.wins)::bigint AS wins,
        sum(dr.losses)::bigint AS losses,
        sum(dr.ties)::bigint AS ties
    FROM core.topic_card_competitive t
    JOIN core.core_deck_result dr
      ON dr.deck_id = t.deck_id
    GROUP BY t.card_id, dr.date_id
),
price AS (
    SELECT
        card_id,
        date_id,
        avg(market_price)::numeric(14,4) AS market_price,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY market_price)::numeric(14,4)
            AS median_market_price,
        min(market_price)::numeric(14,4) AS min_market_price,
        max(market_price)::numeric(14,4) AS max_market_price
    FROM core.core_card_price
    GROUP BY card_id, date_id
),
grain AS (
    SELECT card_id, date_id FROM competitive
    UNION
    SELECT card_id, date_id FROM price
)
INSERT INTO reporting.fact_card_competitive_price (
    card_key,
    date_key,
    total_decks,
    decks_using_card,
    card_copy_count,
    wins,
    losses,
    ties,
    market_price,
    median_market_price,
    min_market_price,
    max_market_price
)
SELECT
    c.card_key,
    d.date_key,
    coalesce(td.total_decks, 0),
    coalesce(comp.decks_using_card, 0),
    coalesce(comp.card_copy_count, 0),
    coalesce(comp.wins, 0),
    coalesce(comp.losses, 0),
    coalesce(comp.ties, 0),
    pr.market_price,
    pr.median_market_price,
    pr.min_market_price,
    pr.max_market_price
FROM grain g
JOIN reporting.dim_card_reporting c
  ON c.card_id = g.card_id
JOIN reporting.dim_date_reporting d
  ON d.date_id = g.date_id
LEFT JOIN total_decks_per_date td
  ON td.date_id = g.date_id
LEFT JOIN competitive comp
  ON comp.card_id = g.card_id
 AND comp.date_id = g.date_id
LEFT JOIN price pr
  ON pr.card_id = g.card_id
 AND pr.date_id = g.date_id;

COMMIT;
