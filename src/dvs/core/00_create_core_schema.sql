-- 00_create_core_schema.sql
-- Creates the CORE schema and all logical CORE tables from the agreed ERM.
--
-- ASSUMPTION:
--   The acquired/source tables are in schema "staging" in the SAME PostgreSQL database.
--   If your source tables are in "public", replace "staging." with "public." in the load scripts.
--
-- The technical table core.card_pokemon_map and the helper views/functions are ETL/integration
-- helpers. They are not additional Reporting dimensions/facts.

BEGIN;

CREATE SCHEMA IF NOT EXISTS core;

-- ---------- Helper function for Card -> Pokemon matching ----------
-- Conservative normalization: punctuation is removed and common TCG suffixes are stripped.
-- Examples: "Charizard ex" -> "charizard", "Pikachu VMAX" -> "pikachu".
-- Regional prefixes (Hisuian, Galarian, etc.) and multi-Pokemon cards are intentionally NOT
-- guessed automatically; those can be mapped manually in core.card_pokemon_map.
CREATE OR REPLACE FUNCTION core.normalize_pokemon_name(p_name text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT regexp_replace(
               regexp_replace(
                   lower(trim(coalesce(p_name, ''))),
                   E'\\s+(ex|gx|v|vmax|vstar|break|prime|lv\\.?x)\\s*$',
                   '',
                   'i'
               ),
               '[^a-z0-9]+',
               '',
               'g'
           );
$$;

-- ---------- Dimensions ----------
CREATE TABLE IF NOT EXISTS core.dim_date (
    date_id      integer PRIMARY KEY,
    full_date    date NOT NULL UNIQUE,
    day          smallint NOT NULL CHECK (day BETWEEN 1 AND 31),
    month        smallint NOT NULL CHECK (month BETWEEN 1 AND 12),
    quarter      smallint NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    year         integer NOT NULL
);

CREATE TABLE IF NOT EXISTS core.dim_pokemon (
    pokemon_id       integer PRIMARY KEY,
    pokemon_name     text NOT NULL,
    hp               integer,
    attack           integer,
    defense          integer,
    special_attack   integer,
    special_defense  integer,
    speed            integer,
    type_one         text,
    type_two         text
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_dim_pokemon_name
    ON core.dim_pokemon (lower(pokemon_name));

CREATE TABLE IF NOT EXISTS core.dim_card (
    card_id       integer PRIMARY KEY,
    card_name     text NOT NULL,
    rarity        text
);

-- ---------- Core support facts ----------
CREATE TABLE IF NOT EXISTS core.core_deck_result (
    deck_id       text PRIMARY KEY,
    date_id       integer NOT NULL REFERENCES core.dim_date(date_id),
    wins          integer NOT NULL DEFAULT 0 CHECK (wins >= 0),
    losses        integer NOT NULL DEFAULT 0 CHECK (losses >= 0),
    ties          integer NOT NULL DEFAULT 0 CHECK (ties >= 0)
);

CREATE INDEX IF NOT EXISTS ix_core_deck_result_date
    ON core.core_deck_result (date_id);

CREATE TABLE IF NOT EXISTS core.core_card_price (
    card_id        integer NOT NULL REFERENCES core.dim_card(card_id),
    printing_type  text NOT NULL,
    date_id        integer NOT NULL REFERENCES core.dim_date(date_id),
    market_price   numeric(14,4) NOT NULL CHECK (market_price >= 0),
    PRIMARY KEY (card_id, printing_type, date_id)
);

CREATE INDEX IF NOT EXISTS ix_core_card_price_date
    ON core.core_card_price (date_id);

-- ---------- Topic tables ----------
CREATE TABLE IF NOT EXISTS core.topic_base_stats_vs_competitive (
    deck_id             text NOT NULL REFERENCES core.core_deck_result(deck_id) ON DELETE CASCADE,
    pokemon_id          integer NOT NULL REFERENCES core.dim_pokemon(pokemon_id),
    pokemon_copy_count  integer NOT NULL CHECK (pokemon_copy_count > 0),
    PRIMARY KEY (deck_id, pokemon_id)
);

CREATE INDEX IF NOT EXISTS ix_topic_base_stats_pokemon
    ON core.topic_base_stats_vs_competitive (pokemon_id);

CREATE TABLE IF NOT EXISTS core.topic_card_competitive (
    deck_id          text NOT NULL REFERENCES core.core_deck_result(deck_id) ON DELETE CASCADE,
    card_id          integer NOT NULL REFERENCES core.dim_card(card_id),
    card_copy_count  integer NOT NULL CHECK (card_copy_count > 0),
    PRIMARY KEY (deck_id, card_id)
);

CREATE INDEX IF NOT EXISTS ix_topic_card_comp_card
    ON core.topic_card_competitive (card_id);

CREATE TABLE IF NOT EXISTS core.topic_pokemon_price (
    pokemon_id  integer NOT NULL REFERENCES core.dim_pokemon(pokemon_id),
    card_id     integer NOT NULL REFERENCES core.dim_card(card_id),
    PRIMARY KEY (pokemon_id, card_id)
);

CREATE INDEX IF NOT EXISTS ix_topic_pokemon_price_card
    ON core.topic_pokemon_price (card_id);

-- ---------- Technical integration helper ----------
-- Supports one card -> one Pokemon and also multi-Pokemon cards (multiple rows per card).
-- Manual mappings survive normal reloads; automatic mappings are rebuilt by 02_load_dimensions_and_mapping.sql.
CREATE TABLE IF NOT EXISTS core.card_pokemon_map (
    card_id       integer NOT NULL REFERENCES core.dim_card(card_id) ON DELETE CASCADE,
    pokemon_id    integer NOT NULL REFERENCES core.dim_pokemon(pokemon_id) ON DELETE CASCADE,
    match_method  text NOT NULL CHECK (match_method IN ('AUTO_NORMALIZED_NAME', 'MANUAL')),
    note          text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (card_id, pokemon_id)
);

COMMENT ON TABLE core.card_pokemon_map IS
'ETL helper for integrating Limitless cards with PokeAPI Pokemon. Not a Reporting fact/dimension.';

-- One-to-one resolved TickerMint product for a Limitless card.
-- A row is returned only if:
--   (1) a Limitless card_id maps to exactly one distinct TickerMint product_id, and
--   (2) that product_id maps back to exactly one distinct Limitless card_id.
CREATE OR REPLACE VIEW core.v_card_product_unique AS
WITH per_card AS (
    SELECT card_id, count(DISTINCT product_id) AS product_count
    FROM staging.card_product
    WHERE card_id IS NOT NULL AND product_id IS NOT NULL
    GROUP BY card_id
),
per_product AS (
    SELECT product_id, count(DISTINCT card_id) AS card_count
    FROM staging.card_product
    WHERE card_id IS NOT NULL AND product_id IS NOT NULL
    GROUP BY product_id
),
ranked AS (
    SELECT
        cp.*,
        row_number() OVER (
            PARTITION BY cp.card_id, cp.product_id
            ORDER BY cp.fetched_at DESC NULLS LAST, cp.product_id
        ) AS rn
    FROM staging.card_product cp
    WHERE cp.card_id IS NOT NULL AND cp.product_id IS NOT NULL
)
SELECT
    r.card_id,
    r.product_id,
    r.group_id,
    r.card_name,
    r.rarity,
    r.search_query,
    r.set_number,
    r.card_set_number,
    r.fetched_at
FROM ranked r
JOIN per_card c USING (card_id)
JOIN per_product p USING (product_id)
WHERE c.product_count = 1
  AND p.card_count = 1
  AND r.rn = 1;

-- Cards for which no Pokemon mapping is currently available.
CREATE OR REPLACE VIEW core.v_unmapped_cards AS
SELECT c.card_id, c.card_name
FROM core.dim_card c
WHERE NOT EXISTS (
    SELECT 1
    FROM core.card_pokemon_map m
    WHERE m.card_id = c.card_id
);

COMMIT;
