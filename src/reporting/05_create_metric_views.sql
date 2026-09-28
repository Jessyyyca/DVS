-- 05_create_metric_views.sql
-- Derived, non-additive KPIs stay in views instead of being stored redundantly in fact tables.

CREATE OR REPLACE VIEW reporting.v_pokemon_competitive_metrics AS
SELECT
    p.pokemon_key,
    p.pokemon_id,
    p.pokemon_name,
    p.base_stat_total,
    p.type_one,
    p.type_two,
    d.date_key,
    d.full_date,
    f.total_decks,
    f.decks_using_pokemon,
    f.pokemon_copy_count,
    f.wins,
    f.losses,
    f.ties,
    f.decks_using_pokemon::numeric / NULLIF(f.total_decks, 0) AS usage_rate,
    f.wins::numeric / NULLIF(f.wins + f.losses + f.ties, 0) AS win_rate,
    (f.wins + 0.5 * f.ties)::numeric
        / NULLIF(f.wins + f.losses + f.ties, 0) AS adjusted_win_rate,
    f.pokemon_copy_count::numeric / NULLIF(f.decks_using_pokemon, 0)
        AS average_copies_when_used
FROM reporting.fact_pokemon_competitive f
JOIN reporting.dim_pokemon_reporting p
  ON p.pokemon_key = f.pokemon_key
JOIN reporting.dim_date_reporting d
  ON d.date_key = f.date_key;

CREATE OR REPLACE VIEW reporting.v_card_competitive_price_metrics AS
SELECT
    c.card_key,
    c.card_id,
    c.card_name,
    c.rarity,
    d.date_key,
    d.full_date,
    f.total_decks,
    f.decks_using_card,
    f.card_copy_count,
    f.wins,
    f.losses,
    f.ties,
    f.market_price,
    f.min_market_price,
    f.max_market_price,
    f.decks_using_card::numeric / NULLIF(f.total_decks, 0) AS usage_rate,
    f.wins::numeric / NULLIF(f.wins + f.losses + f.ties, 0) AS win_rate,
    (f.wins + 0.5 * f.ties)::numeric
        / NULLIF(f.wins + f.losses + f.ties, 0) AS adjusted_win_rate,
    f.card_copy_count::numeric / NULLIF(f.decks_using_card, 0)
        AS average_copies_when_used
FROM reporting.fact_card_competitive_price f
JOIN reporting.dim_card_reporting c
  ON c.card_key = f.card_key
JOIN reporting.dim_date_reporting d
  ON d.date_key = f.date_key;

-- Monthly card-price metrics requested in Star_Schemas_Reporting.md.
-- price_change_N_month(s) is an absolute change in market price.
-- *_pct provides the corresponding relative change.
CREATE OR REPLACE VIEW reporting.v_card_monthly_price_metrics AS
WITH daily AS (
    SELECT
        f.card_key,
        d.full_date,
        f.market_price
    FROM reporting.fact_card_competitive_price f
    JOIN reporting.dim_date_reporting d
      ON d.date_key = f.date_key
    WHERE f.market_price IS NOT NULL
),
monthly_avg AS (
    SELECT
        card_key,
        date_trunc('month', full_date)::date AS month_start,
        avg(market_price)::numeric(14,4) AS average_month_price
    FROM daily
    GROUP BY card_key, date_trunc('month', full_date)::date
),
month_end AS (
    SELECT DISTINCT ON (card_key, date_trunc('month', full_date)::date)
        card_key,
        date_trunc('month', full_date)::date AS month_start,
        market_price::numeric(14,4) AS month_end_price
    FROM daily
    ORDER BY card_key, date_trunc('month', full_date)::date, full_date DESC
),
monthly AS (
    SELECT
        a.card_key,
        a.month_start,
        a.average_month_price,
        e.month_end_price
    FROM monthly_avg a
    JOIN month_end e USING (card_key, month_start)
)
SELECT
    c.card_key,
    c.card_id,
    c.card_name,
    m.month_start,
    m.average_month_price,
    m.month_end_price,
    (m.month_end_price - p1.month_end_price)::numeric(14,4) AS price_change_1_month,
    (m.month_end_price - p3.month_end_price)::numeric(14,4) AS price_change_3_months,
    (m.month_end_price - p12.month_end_price)::numeric(14,4) AS price_change_12_months,
    (m.month_end_price - p1.month_end_price) / NULLIF(p1.month_end_price, 0) AS price_change_1_month_pct,
    (m.month_end_price - p3.month_end_price) / NULLIF(p3.month_end_price, 0) AS price_change_3_months_pct,
    (m.month_end_price - p12.month_end_price) / NULLIF(p12.month_end_price, 0) AS price_change_12_months_pct
FROM monthly m
JOIN reporting.dim_card_reporting c
  ON c.card_key = m.card_key
LEFT JOIN monthly p1
  ON p1.card_key = m.card_key
 AND p1.month_start = (m.month_start - interval '1 month')::date
LEFT JOIN monthly p3
  ON p3.card_key = m.card_key
 AND p3.month_start = (m.month_start - interval '3 months')::date
LEFT JOIN monthly p12
  ON p12.card_key = m.card_key
 AND p12.month_start = (m.month_start - interval '12 months')::date;
