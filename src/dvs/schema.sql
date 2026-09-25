-- DVS schema bootstrap. Runs against $DVS_DB_DSN.
--
-- Purely additive: CREATE TABLE IF NOT EXISTS for every importer-owned
-- table plus supporting CREATE UNIQUE INDEX / CREATE INDEX IF NOT EXISTS.
-- No DROP, TRUNCATE, or RENAME -- rerunning against an existing
-- database never destroys rows. If you need a destructive rebuild,
-- drop the target tables by hand before applying this file.
--
-- Output for `dvs generate-sql`. The importers ship their own
-- setup_schema() that creates only their own tables, so this file
-- is mainly useful for fresh installs and CI.
--
-- pokemon_id is intentionally NOT linked from card_product.

BEGIN;

CREATE TABLE IF NOT EXISTS type (
    url_id  TEXT PRIMARY KEY,
    name    TEXT NOT NULL
);

-- ability / move / pokemon_ability / pokemon_move were dropped manually
-- on 2026-09-25 (see /tmp/drop_ability_move.py for the one-shot SQL).
-- Per-product ability/move metadata from PokeAPI is intentionally no
-- longer captured by DVS.

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

-- Limitless card identity. Populated by `dvs limitless`. Kept so deck_card
-- can still reference card_id.
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

-- TickerMint products: exactly one row per Limitless card (PK = card_id).
-- product_id is TickerMint's id; it is NULL when the most recent search
-- returned no candidate, which lets us record the miss in the same row
-- that a future successful search will overwrite. The UNIQUE constraint
-- still holds because Postgres treats NULLs as distinct in unique
-- indexes -- so two different cards can each have a NULL product_id
-- (both unmatched), but the same non-null product_id may only appear
-- once across the table.
--
-- set_number         = TickerMint set denominator / size used in the
--                      search query, e.g. "165" for SVI.
-- card_set_number    = the card's position within that set, e.g. "199".
-- search_query       = literal query string the importer used (NULL when
--                      the run could not even build a query -- e.g.
--                      unmapped set_code or missing card_number).
CREATE TABLE IF NOT EXISTS card_product (
    card_id          BIGINT PRIMARY KEY REFERENCES card(card_id) ON DELETE CASCADE,
    product_id       BIGINT UNIQUE,
    group_id         BIGINT,
    card_name        TEXT,
    rarity           TEXT,
    search_query     TEXT,
    set_number       TEXT,
    card_set_number  TEXT,
    fetched_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_card_product_product ON card_product (product_id);
CREATE INDEX IF NOT EXISTS ix_card_product_group   ON card_product (group_id);
CREATE INDEX IF NOT EXISTS ix_card_product_name    ON card_product (lower(card_name));

-- A TickerMint product has 1..N printings (Normal, Holofoil, ...).
-- printing_id is TickerMint's internal id (nullable when the endpoint
-- omits it); printing_type is the human-readable label.
CREATE TABLE IF NOT EXISTS printing (
    product_id    BIGINT NOT NULL REFERENCES card_product(product_id) ON DELETE CASCADE,
    printing_id   BIGINT,
    printing_type TEXT NOT NULL,
    PRIMARY KEY (product_id, printing_type),
    UNIQUE (product_id, printing_id)
);

CREATE INDEX IF NOT EXISTS ix_printing_product ON printing (product_id);

CREATE TABLE IF NOT EXISTS daily_price (
    product_id    BIGINT      NOT NULL,
    printing_id   BIGINT,
    printing_type TEXT        NOT NULL,
    price_date    DATE        NOT NULL,
    market_price  NUMERIC(12,4) NOT NULL CHECK (market_price >= 0),
    PRIMARY KEY (product_id, printing_type, price_date),
    FOREIGN KEY (product_id, printing_type)
        REFERENCES printing(product_id, printing_type) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_daily_price_date    ON daily_price (price_date);
CREATE INDEX IF NOT EXISTS ix_daily_price_product ON daily_price (product_id);

COMMIT;
