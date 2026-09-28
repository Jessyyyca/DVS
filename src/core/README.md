# Core ETL v02 (single PostgreSQL database)

This is the second Core-layer attempt. It intentionally lives at repository root in `core/`, beside the first attempt under `src/dvs/core/`, so both versions can be compared.

## Architecture

All data stays in one PostgreSQL database.

- Acquired/staging tables remain in `public` (`card`, `card_product`, `daily_price`, `deck`, `deck_card`, `pokemon`, `pokemon_type`, `printing`, `type`).
- The warehouse Core is isolated in the `core` schema.
- No `postgres_fdw`, second database, or second Docker service is required.

## Execution order

```sh
psql "$DVS_DB_DSN" -f core/00_create_core_schema.sql
psql "$DVS_DB_DSN" -f core/01_staging_quality_checks.sql
psql "$DVS_DB_DSN" -f core/02_load_dimensions_and_mapping.sql
# optional: edit/run 03_manual_card_pokemon_mapping.sql for unmapped cards
psql "$DVS_DB_DSN" -f core/04_load_core_support_facts.sql
psql "$DVS_DB_DSN" -f core/05_load_topics.sql
psql "$DVS_DB_DSN" -f core/06_validate_core.sql
```

For a refresh while preserving manually curated card-to-Pokemon mappings:

```sh
psql "$DVS_DB_DSN" -f core/07_reload_core_data.sql
psql "$DVS_DB_DSN" -f core/02_load_dimensions_and_mapping.sql
psql "$DVS_DB_DSN" -f core/04_load_core_support_facts.sql
psql "$DVS_DB_DSN" -f core/05_load_topics.sql
psql "$DVS_DB_DSN" -f core/06_validate_core.sql
```

## Core grain

- `core.core_deck_result`: one deck.
- `core.core_card_price`: one card × printing type × exact date.
- `core.topic_base_stats_vs_competitive`: one deck × Pokemon.
- `core.topic_card_competitive`: one deck × card.
- `core.topic_pokemon_price`: one Pokemon × card.

`core.card_pokemon_map` is a technical integration table because Limitless cards and PokeAPI Pokemon do not share an ID.

Monthly aggregates, usage rates, win rates, and price changes are derived later in Reporting/Business, not stored in Core.

## Type order caveat

The current staging table `pokemon_type(pokemon_id, type_url)` does not keep PokeAPI's `slot`. Therefore `type_one` and `type_two` are assigned deterministically by alphabetic order. If the distinction between primary/secondary type matters, add `slot` to staging and adapt the loader.
