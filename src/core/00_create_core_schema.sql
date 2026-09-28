-- pg_trgm provides the similarity() function used by the fuzzy Card -> Pokemon fallback
-- in 02_load_dimensions_and_mapping.sql.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

BEGIN;

CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE IF NOT EXISTS core.dim_date (
    date_id     INT PRIMARY KEY,
    full_date   DATE NOT NULL UNIQUE,
    day         INT NOT NULL,
    month       INT NOT NULL,
    quarter     INT NOT NULL,
    year        INT NOT NULL
);

CREATE TABLE IF NOT EXISTS core.dim_pokemon (
    pokemon_id      INT PRIMARY KEY,
    pokemon_name    TEXT NOT NULL,
    hp              INT,
    attack          INT,
    defense         INT,
    special_attack  INT,
    special_defense INT,
    speed           INT,
    type_one        TEXT,
    type_two        TEXT
);

CREATE TABLE IF NOT EXISTS core.dim_card (
    card_id     BIGINT PRIMARY KEY,
    card_name   TEXT NOT NULL,
    rarity      TEXT
);

CREATE TABLE IF NOT EXISTS core.core_deck_result (
    deck_id  UUID PRIMARY KEY,
    date_id  INT NOT NULL REFERENCES core.dim_date(date_id),
    wins     INT NOT NULL DEFAULT 0,
    losses   INT NOT NULL DEFAULT 0,
    ties     INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS core.core_card_price (
    card_id        BIGINT NOT NULL REFERENCES core.dim_card(card_id),
    printing_type  TEXT NOT NULL,
    date_id        INT NOT NULL REFERENCES core.dim_date(date_id),
    market_price   NUMERIC(12,4) NOT NULL CHECK (market_price >= 0),
    PRIMARY KEY (card_id, printing_type, date_id)
);

CREATE TABLE IF NOT EXISTS core.card_pokemon_map (
    card_id      BIGINT NOT NULL REFERENCES core.dim_card(card_id) ON DELETE CASCADE,
    pokemon_id   INT NOT NULL REFERENCES core.dim_pokemon(pokemon_id) ON DELETE CASCADE,
    match_method TEXT NOT NULL CHECK (match_method IN ('automatic','automatic_fuzzy','manual')),
    PRIMARY KEY (card_id, pokemon_id)
);

CREATE TABLE IF NOT EXISTS core.topic_base_stats_vs_competitive (
    deck_id             UUID NOT NULL REFERENCES core.core_deck_result(deck_id) ON DELETE CASCADE,
    pokemon_id          INT NOT NULL REFERENCES core.dim_pokemon(pokemon_id),
    pokemon_copy_count  INT NOT NULL CHECK (pokemon_copy_count > 0),
    PRIMARY KEY (deck_id, pokemon_id)
);

CREATE TABLE IF NOT EXISTS core.topic_card_competitive (
    deck_id          UUID NOT NULL REFERENCES core.core_deck_result(deck_id) ON DELETE CASCADE,
    card_id          BIGINT NOT NULL REFERENCES core.dim_card(card_id),
    card_copy_count  INT NOT NULL CHECK (card_copy_count > 0),
    PRIMARY KEY (deck_id, card_id)
);

CREATE TABLE IF NOT EXISTS core.topic_pokemon_price (
    pokemon_id  INT NOT NULL REFERENCES core.dim_pokemon(pokemon_id),
    card_id     BIGINT NOT NULL REFERENCES core.dim_card(card_id),
    PRIMARY KEY (pokemon_id, card_id)
);

CREATE INDEX IF NOT EXISTS ix_core_deck_result_date
    ON core.core_deck_result(date_id);
CREATE INDEX IF NOT EXISTS ix_core_card_price_date
    ON core.core_card_price(date_id);
CREATE INDEX IF NOT EXISTS ix_core_card_price_card
    ON core.core_card_price(card_id);
CREATE INDEX IF NOT EXISTS ix_core_map_pokemon
    ON core.card_pokemon_map(pokemon_id);

-- Existing deployments: widen the match_method CHECK to also admit 'automatic_fuzzy'
-- (rows produced by the pg_trgm similarity() fallback in 02_load_dimensions_and_mapping.sql).
-- No-op on a fresh install because the CREATE TABLE above already declares the wider CHECK.
ALTER TABLE core.card_pokemon_map
    DROP CONSTRAINT IF EXISTS card_pokemon_map_match_method_check;
ALTER TABLE core.card_pokemon_map
    ADD CONSTRAINT card_pokemon_map_match_method_check
    CHECK (match_method IN ('automatic','automatic_fuzzy','manual'));

COMMIT;
