-- 05_create_metric_views.sql
-- Analysis-oriented views for the three questions in the repository README.
-- Non-additive KPIs are derived here instead of being stored redundantly in facts.

-- View shapes changed during Reporting development; drop first so the script is
-- safely rerunnable even when an older version of these views already exists.
DROP VIEW IF EXISTS reporting.v_card_monthly_price_metrics;
DROP VIEW IF EXISTS reporting.v_card_competitive_price_metrics;
DROP VIEW IF EXISTS reporting.v_pokemon_card_price_metrics;
DROP VIEW IF EXISTS reporting.v_pokemon_competitive_metrics;

-- ---------------------------------------------------------------------------
-- Analysis scenario 3:
-- Tournament usage/performance vs Pokemon type and base stats.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW reporting.v_pokemon_competitive_metrics AS
SELECT
    p.pokemon_key,
    p.pokemon_id,
    p.pokemon_name,
    p.hp,
    p.attack,
    p.defense,
    p.special_attack,
    p.special_defense,
    p.speed,
    p.base_stat_total,
    p.type_one,
    p.type_two,
    d.date_key,
    d.full_date,
    d.weekday,
    d.monthday,
    d.month,
    d.quarter,
    d.year,
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

-- ---------------------------------------------------------------------------
-- Analysis scenario 1:
-- Card prices vs Pokemon type and base stats.
-- One row for every available Pokemon x Card x price-date observation.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW reporting.v_pokemon_card_price_metrics AS
SELECT
    p.pokemon_key,
    p.pokemon_id,
    p.pokemon_name,
    p.hp,
    p.attack,
    p.defense,
    p.special_attack,
    p.special_defense,
    p.speed,
    p.base_stat_total,
    p.type_one,
    p.type_two,
    c.card_key,
    c.card_id,
    c.card_name,
    c.set_name,
    c.rarity,
    d.date_key,
    d.full_date,
    d.weekday,
    d.monthday,
    d.month,
    d.quarter,
    d.year,
    f.market_price AS average_price,
    f.median_market_price AS median_price,
    f.min_market_price AS min_price,
    f.max_market_price AS max_price
FROM reporting.fact_pokemon_card_price f
JOIN reporting.dim_pokemon_reporting p
  ON p.pokemon_key = f.pokemon_key
JOIN reporting.dim_card_reporting c
  ON c.card_key = f.card_key
JOIN reporting.dim_date_reporting d
  ON d.date_key = f.date_key;

-- ---------------------------------------------------------------------------
-- Analysis scenario 2:
-- Card prices vs tournament usage/performance.
--
-- IMPORTANT: this view is PRICE-TIMELINE driven. It returns every available
-- daily price observation for a card, not only the dates on which the card was
-- played in a tournament. Competitive metrics are overlaid on that timeline.
-- This lets a chart show price before/after periods of high usage or win rate.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW reporting.v_card_competitive_price_metrics AS
WITH tournament_daily AS (
    -- total_decks is repeated in the fact for each card/date. MAX removes that
    -- repetition and gives one tournament denominator per date.
    SELECT
        date_key,
        max(total_decks)::bigint AS total_decks
    FROM reporting.fact_card_competitive_price
    WHERE total_decks > 0
    GROUP BY date_key
),
card_competitive_daily AS (
    SELECT
        card_key,
        date_key,
        decks_using_card,
        card_copy_count,
        wins,
        losses,
        ties
    FROM reporting.fact_card_competitive_price
    WHERE total_decks > 0
),
price_daily AS (
    SELECT
        card_key,
        date_key,
        market_price,
        median_market_price,
        min_market_price,
        max_market_price
    FROM reporting.fact_card_competitive_price
    WHERE market_price IS NOT NULL
),
price_timeline AS (
    SELECT
        p.*,
        d.full_date,
        lag(p.market_price) OVER (
            PARTITION BY p.card_key ORDER BY d.full_date
        ) AS previous_average_price,
        lag(d.full_date) OVER (
            PARTITION BY p.card_key ORDER BY d.full_date
        ) AS previous_price_date
    FROM price_daily p
    JOIN reporting.dim_date_reporting d
      ON d.date_key = p.date_key
)
SELECT
    c.card_key,
    c.card_id,
    c.card_name,
    c.rarity,
    d.date_key,
    d.full_date,
    d.weekday,
    d.monthday,
    d.month,
    d.quarter,
    d.year,

    -- Daily price history: one row for each actual price observation.
    p.market_price AS average_price,
    p.median_market_price AS median_price,
    p.min_market_price AS min_price,
    p.max_market_price AS max_price,
    p.previous_price_date,
    p.previous_average_price,
    (p.market_price - p.previous_average_price)::numeric(14,4)
        AS price_change_from_previous_observation,
    (p.market_price - p.previous_average_price)
        / NULLIF(p.previous_average_price, 0)
        AS price_change_from_previous_observation_pct,

    -- Competitive activity on this exact price date. NULL total_decks means no
    -- tournament observation exists for that date; zero decks_using_card means
    -- tournaments existed but this card was not used.
    (td.total_decks IS NOT NULL) AS has_tournament_observation,
    td.total_decks,
    CASE WHEN td.total_decks IS NOT NULL
         THEN coalesce(cd.decks_using_card, 0)
    END AS decks_using_card,
    CASE WHEN td.total_decks IS NOT NULL
         THEN coalesce(cd.card_copy_count, 0)
    END AS card_copy_count,
    CASE WHEN td.total_decks IS NOT NULL
         THEN coalesce(cd.wins, 0)
    END AS wins,
    CASE WHEN td.total_decks IS NOT NULL
         THEN coalesce(cd.losses, 0)
    END AS losses,
    CASE WHEN td.total_decks IS NOT NULL
         THEN coalesce(cd.ties, 0)
    END AS ties,
    coalesce(cd.decks_using_card, 0)::numeric
        / NULLIF(td.total_decks, 0) AS usage_rate,
    cd.wins::numeric
        / NULLIF(cd.wins + cd.losses + cd.ties, 0) AS win_rate,
    (cd.wins + 0.5 * cd.ties)::numeric
        / NULLIF(cd.wins + cd.losses + cd.ties, 0) AS adjusted_win_rate,
    cd.card_copy_count::numeric
        / NULLIF(cd.decks_using_card, 0) AS average_copies_when_used,

    -- Rolling competitive periods ending on this PRICE date. These fields are
    -- useful for testing whether price changes follow sustained usage/success.
    r7.total_decks AS total_decks_7d,
    r7.decks_using_card AS decks_using_card_7d,
    r7.card_copy_count AS card_copy_count_7d,
    r7.wins AS wins_7d,
    r7.losses AS losses_7d,
    r7.ties AS ties_7d,
    r7.decks_using_card::numeric / NULLIF(r7.total_decks, 0) AS usage_rate_7d,
    r7.wins::numeric / NULLIF(r7.wins + r7.losses + r7.ties, 0) AS win_rate_7d,
    (r7.wins + 0.5 * r7.ties)::numeric
        / NULLIF(r7.wins + r7.losses + r7.ties, 0) AS adjusted_win_rate_7d,

    r30.total_decks AS total_decks_30d,
    r30.decks_using_card AS decks_using_card_30d,
    r30.card_copy_count AS card_copy_count_30d,
    r30.wins AS wins_30d,
    r30.losses AS losses_30d,
    r30.ties AS ties_30d,
    r30.decks_using_card::numeric / NULLIF(r30.total_decks, 0) AS usage_rate_30d,
    r30.wins::numeric / NULLIF(r30.wins + r30.losses + r30.ties, 0) AS win_rate_30d,
    (r30.wins + 0.5 * r30.ties)::numeric
        / NULLIF(r30.wins + r30.losses + r30.ties, 0) AS adjusted_win_rate_30d,

    -- Most recent date at/before the price observation on which the card was
    -- actually used. This makes "price after competitive success" easy to plot.
    last_used.last_used_date,
    (d.full_date - last_used.last_used_date) AS days_since_last_use,
    last_used.last_usage_rate,
    last_used.last_win_rate,
    last_used.last_adjusted_win_rate
FROM price_timeline p
JOIN reporting.dim_card_reporting c
  ON c.card_key = p.card_key
JOIN reporting.dim_date_reporting d
  ON d.date_key = p.date_key
LEFT JOIN tournament_daily td
  ON td.date_key = p.date_key
LEFT JOIN card_competitive_daily cd
  ON cd.card_key = p.card_key
 AND cd.date_key = p.date_key
LEFT JOIN LATERAL (
    SELECT
        sum(td7.total_decks)::bigint AS total_decks,
        sum(coalesce(cd7.decks_using_card, 0))::bigint AS decks_using_card,
        sum(coalesce(cd7.card_copy_count, 0))::bigint AS card_copy_count,
        sum(coalesce(cd7.wins, 0))::bigint AS wins,
        sum(coalesce(cd7.losses, 0))::bigint AS losses,
        sum(coalesce(cd7.ties, 0))::bigint AS ties
    FROM tournament_daily td7
    JOIN reporting.dim_date_reporting d7
      ON d7.date_key = td7.date_key
    LEFT JOIN card_competitive_daily cd7
      ON cd7.card_key = p.card_key
     AND cd7.date_key = td7.date_key
    WHERE d7.full_date BETWEEN d.full_date - 6 AND d.full_date
) r7 ON true
LEFT JOIN LATERAL (
    SELECT
        sum(td30.total_decks)::bigint AS total_decks,
        sum(coalesce(cd30.decks_using_card, 0))::bigint AS decks_using_card,
        sum(coalesce(cd30.card_copy_count, 0))::bigint AS card_copy_count,
        sum(coalesce(cd30.wins, 0))::bigint AS wins,
        sum(coalesce(cd30.losses, 0))::bigint AS losses,
        sum(coalesce(cd30.ties, 0))::bigint AS ties
    FROM tournament_daily td30
    JOIN reporting.dim_date_reporting d30
      ON d30.date_key = td30.date_key
    LEFT JOIN card_competitive_daily cd30
      ON cd30.card_key = p.card_key
     AND cd30.date_key = td30.date_key
    WHERE d30.full_date BETWEEN d.full_date - 29 AND d.full_date
) r30 ON true
LEFT JOIN LATERAL (
    SELECT
        du.full_date AS last_used_date,
        cd_last.decks_using_card::numeric / NULLIF(td_last.total_decks, 0)
            AS last_usage_rate,
        cd_last.wins::numeric
            / NULLIF(cd_last.wins + cd_last.losses + cd_last.ties, 0)
            AS last_win_rate,
        (cd_last.wins + 0.5 * cd_last.ties)::numeric
            / NULLIF(cd_last.wins + cd_last.losses + cd_last.ties, 0)
            AS last_adjusted_win_rate
    FROM card_competitive_daily cd_last
    JOIN reporting.dim_date_reporting du
      ON du.date_key = cd_last.date_key
    JOIN tournament_daily td_last
      ON td_last.date_key = cd_last.date_key
    WHERE cd_last.card_key = p.card_key
      AND cd_last.decks_using_card > 0
      AND du.full_date <= d.full_date
    ORDER BY du.full_date DESC
    LIMIT 1
) last_used ON true;

-- ---------------------------------------------------------------------------
-- Monthly price metrics for scenario 2.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW reporting.v_card_monthly_price_metrics AS
WITH daily AS (
    SELECT
        f.card_key,
        d.full_date,
        f.market_price,
        f.median_market_price,
        f.min_market_price,
        f.max_market_price
    FROM reporting.fact_card_competitive_price f
    JOIN reporting.dim_date_reporting d
      ON d.date_key = f.date_key
    WHERE f.market_price IS NOT NULL
),
monthly_stats AS (
    SELECT
        card_key,
        date_trunc('month', full_date)::date AS month_start,
        avg(market_price)::numeric(14,4) AS average_month_price,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY market_price)::numeric(14,4)
            AS median_month_price,
        min(min_market_price)::numeric(14,4) AS min_month_price,
        max(max_market_price)::numeric(14,4) AS max_month_price
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
        s.card_key,
        s.month_start,
        s.average_month_price,
        s.median_month_price,
        s.min_month_price,
        s.max_month_price,
        e.month_end_price
    FROM monthly_stats s
    JOIN month_end e USING (card_key, month_start)
)
SELECT
    c.card_key,
    c.card_id,
    c.card_name,
    m.month_start,
    m.average_month_price,
    m.median_month_price,
    m.min_month_price,
    m.max_month_price,
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
