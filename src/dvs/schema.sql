-- DVS schema bootstrap. Runs against $DVS_DB_DSN.
--
-- Option A: drops printing + daily_price and recreates them in the
-- ERM-faithful shape (printing_id PK, daily_price FK on printing_id).
-- Data in printing / daily_price is lost.
--
-- pokemon_id is intentionally NOT linked from card_product.

BEGIN;

-- Drop legacy / half-installed tables first so the ERM-faithful shape
-- can be installed cleanly even when a previous run left the old PK.
DROP TABLE IF EXISTS daily_price    CASCADE;
DROP TABLE IF EXISTS printing       CASCADE;
DROP TABLE IF EXISTS limitless_card_map CASCADE;
DROP TABLE IF EXISTS deck_card      CASCADE;
DROP TABLE IF EXISTS deck           CASCADE;
DROP TABLE IF EXISTS card           CASCADE;
DROP TABLE IF EXISTS card_product   CASCADE;
DROP TABLE IF EXISTS set            CASCADE;
DROP TABLE IF EXISTS pokemon_move   CASCADE;
DROP TABLE IF EXISTS pokemon_ability CASCADE;
DROP TABLE IF EXISTS pokemon_type   CASCADE;
DROP TABLE IF EXISTS pokemon        CASCADE;
DROP TABLE IF EXISTS type           CASCADE;
DROP TABLE IF EXISTS ability        CASCADE;
DROP TABLE IF EXISTS move           CASCADE;

CREATE TABLE IF NOT EXISTS type (
    url_id  TEXT PRIMARY KEY,
    name    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ability (
    url_id  TEXT PRIMARY KEY,
    name    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS move (
    url_id  TEXT PRIMARY KEY,
    name    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pokemon (
    id              INT PRIMARY KEY,
    name            TEXT NOT NULL,
    base_experience INT,
    height          INT,
    is_default      BOOLEAN,
    weight          INT,
    "order"         INT,
    hp              INT,
    attack          INT,
    defense INT,
    special_attack  INT,
    special_defense INT,
    speed           INT
);
CREATE INDEX IF NOT EXISTS ix_pokemon_name ON pokemon (name);

CREATE TABLE IF NOT EXISTS pokemon_type (
    pokemon_id INT  NOT NULL REFERENCES pokemon(id) ON DELETE CASCADE,
    type_url   TEXT NOT NULL REFERENCES type(url_id) ON DELETE CASCADE,
    PRIMARY KEY (pokemon_id, type_url)
);

CREATE TABLE IF NOT EXISTS pokemon_ability (
    pokemon_id  INT NOT NULL REFERENCES pokemon(id) ON DELETE CASCADE,
    ability_url TEXT NOT NULL REFERENCES ability(url_id) ON DELETE CASCADE,
    PRIMARY KEY (pokemon_id, ability_url)
);

CREATE TABLE IF NOT EXISTS pokemon_move (
    pokemon_id INT  NOT NULL REFERENCES pokemon(id) ON DELETE CASCADE,
    move_url   TEXT NOT NULL REFERENCES move(url_id) ON DELETE CASCADE,
    PRIMARY KEY (pokemon_id, move_url)
);

CREATE TABLE IF NOT EXISTS set (
    group_id  BIGINT PRIMARY KEY,
    set_name  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS card_product (
    product_id       BIGINT PRIMARY KEY,
    group_id         BIGINT NOT NULL REFERENCES set(group_id) ON DELETE RESTRICT,
    card_name        TEXT NOT NULL,
    collector_number TEXT,
    rarity           TEXT
);
CREATE INDEX IF NOT EXISTS ix_card_product_group ON card_product (group_id);

CREATE TABLE IF NOT EXISTS card (
    card_id      BIGSERIAL PRIMARY KEY,
    card_name    TEXT NOT NULL,
    set_code     TEXT,
    card_number  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_card_identity
    ON card (lower(card_name), COALESCE(set_code, ''), COALESCE(card_number, ''));

CREATE TABLE IF NOT EXISTS deck (
    deck_id            UUID PRIMARY KEY,
    source_event_id    TEXT NOT NULL,
    event_date         DATE NOT NULL,
    format             TEXT NOT NULL,
    player_id          TEXT,
    wins               INT,
    losses             INT,
    ties               INT,
    placings           INT,
    deck_archtype_id   TEXT,
    deck_archtype_name TEXT,
    play_date          DATE
);
CREATE INDEX IF NOT EXISTS ix_deck_date_format ON deck (event_date, format);
CREATE INDEX IF NOT EXISTS ix_deck_player      ON deck (player_id);
CREATE INDEX IF NOT EXISTS ix_deck_archtype    ON deck (deck_archtype_id);

CREATE TABLE IF NOT EXISTS deck_card (
    deck_id  UUID NOT NULL REFERENCES deck(deck_id) ON DELETE CASCADE,
    card_id  BIGINT  NOT NULL REFERENCES card(card_id) ON DELETE RESTRICT,
    quantity SMALLINT NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (deck_id, card_id)
);

-- Drop legacy tables so the ERM-faithful shape can be installed.
DROP TABLE IF EXISTS daily_price CASCADE;
DROP TABLE IF EXISTS printing    CASCADE;

CREATE TABLE IF NOT EXISTS printing (
    product_id    BIGINT NOT NULL REFERENCES card_product(product_id) ON DELETE CASCADE,
    printing_id   BIGINT NOT NULL,
    printing_type TEXT NOT NULL,
    PRIMARY KEY (product_id, printing_id),
    UNIQUE (product_id, printing_type)
);

CREATE TABLE IF NOT EXISTS daily_price (
    product_id    BIGINT      NOT NULL,
    printing_id   BIGINT      NOT NULL,
    price_date    DATE        NOT NULL,
    market_price  NUMERIC(12,4) NOT NULL CHECK (market_price >= 0),
    PRIMARY KEY (product_id, printing_id, price_date),
    FOREIGN KEY (product_id, printing_id)
        REFERENCES printing(product_id, printing_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_daily_price_date    ON daily_price (price_date);
CREATE INDEX IF NOT EXISTS ix_daily_price_product ON daily_price (product_id);

-- 1:N: one Limitless card identity can map to many TickerMint products
-- (all candidates the search returned). match_kind records whether the
-- collector number also matched (exact_number) or only the name matched
-- (exact_name), so reviewers can triage without re-querying the API.
-- The matcher wipes existing rows for a card_id before re-inserting so
-- the table stays in lockstep with what TickerMint returned on the most
-- recent run.
CREATE TABLE IF NOT EXISTS limitless_card_map (
    limitless_card_id BIGINT NOT NULL REFERENCES card(card_id) ON DELETE CASCADE,
    product_id        BIGINT NOT NULL REFERENCES card_product(product_id) ON DELETE CASCADE,
    match_kind        TEXT NOT NULL CHECK (
        match_kind IN ('exact_number', 'exact_name', 'fuzzy')
    ),
    -- 0..100 similarity score from rapidfuzz for fuzzy rows; NULL for
    -- the exact tiers so existing rows stay valid on schema migration.
    similarity        INT CHECK (
        similarity IS NULL OR (similarity BETWEEN 0 AND 100)
    ),
    search_query      TEXT NOT NULL,
    captured_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (limitless_card_id, product_id)
);
CREATE INDEX IF NOT EXISTS ix_limitless_card_map_product
    ON limitless_card_map (product_id);
CREATE INDEX IF NOT EXISTS ix_limitless_card_map_similarity
    ON limitless_card_map (similarity);

COMMIT;