-- 02_load_fact_pokemon_competitive.sql
-- Star 1: Pokemon base stats vs competitive performance.
-- Grain: one Pokemon x one date.

BEGIN;

TRUNCATE TABLE reporting.fact_pokemon_competitive;

WITH total_decks_per_date AS (
    SELECT
        date_id,
        count(DISTINCT deck_id)::bigint AS total_decks
    FROM core.core_deck_result
    GROUP BY date_id
),
pokemon_usage AS (
    SELECT
        t.pokemon_id,
        dr.date_id,
        count(DISTINCT t.deck_id)::bigint AS decks_using_pokemon,
        sum(t.pokemon_copy_count)::bigint AS pokemon_copy_count,
        sum(dr.wins)::bigint AS wins,
        sum(dr.losses)::bigint AS losses,
        sum(dr.ties)::bigint AS ties
    FROM core.topic_base_stats_vs_competitive t
    JOIN core.core_deck_result dr
      ON dr.deck_id = t.deck_id
    GROUP BY t.pokemon_id, dr.date_id
)
INSERT INTO reporting.fact_pokemon_competitive (
    pokemon_key,
    date_key,
    total_decks,
    decks_using_pokemon,
    pokemon_copy_count,
    wins,
    losses,
    ties
)
SELECT
    p.pokemon_key,
    d.date_key,
    td.total_decks,
    u.decks_using_pokemon,
    u.pokemon_copy_count,
    u.wins,
    u.losses,
    u.ties
FROM pokemon_usage u
JOIN total_decks_per_date td
  ON td.date_id = u.date_id
JOIN reporting.dim_pokemon_reporting p
  ON p.pokemon_id = u.pokemon_id
JOIN reporting.dim_date_reporting d
  ON d.date_id = u.date_id;

COMMIT;
