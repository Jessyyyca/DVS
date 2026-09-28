# Pokémon DWH – CORE load scripts

These scripts implement the CORE ERM supplied in the project and fill it from the PostgreSQL staging tables.

## Assumptions

- Source tables are in schema `staging` in the **same PostgreSQL database** as the Core schema.
- If your tables are currently in `public`, replace `staging.` with `public.` in the scripts (or move them to a staging schema).
- PostgreSQL column names are assumed to be snake_case: `special_attack`, `special_defense`, etc.
- `deck.play_date` is preferred for competitive dates; `event_date` is used as a fallback when `play_date` is NULL.
- `date_id` is a stable integer in `YYYYMMDD` form, e.g. `20260928`.

If Staging and Core are in **different PostgreSQL databases**, normal SQL cannot directly join them. In that case use `postgres_fdw`, `dblink`, or copy the staging tables into the DWH database first.

## Run order

1. `00_create_core_schema.sql`
2. `01_staging_quality_checks.sql` – inspect the output before continuing
3. `02_load_dimensions_and_mapping.sql`
4. Review `core.v_unmapped_cards`
5. Optionally edit/run `03_manual_card_pokemon_mapping_template.sql`
6. `04_load_core_support_facts.sql`
7. `05_load_topics.sql`
8. `06_validate_core.sql`

If you add manual mappings after step 7, just rerun `05_load_topics.sql`.

For a later full data refresh, run `07_reload_core_data.sql` followed by steps 2, 4, 5, 6 and 7 as appropriate.

## Important modelling decisions

### 1. TickerMint mapping

`card_product` may contain more than one search result for one Limitless card. The helper view `core.v_card_product_unique` only accepts a mapping when it is one-to-one in both directions:

- one Limitless `card_id` -> exactly one TickerMint `product_id`
- that TickerMint `product_id` -> exactly one Limitless `card_id`

Ambiguous mappings are intentionally excluded from `CORE_CARD_PRICE`; they should be corrected in staging rather than guessed.

### 2. Card -> Pokémon mapping

The technical table `core.card_pokemon_map` is used to make the integration reproducible. Automatic matching is conservative:

- lowercase
- punctuation ignored
- common suffixes such as `ex`, `GX`, `V`, `VMAX`, `VSTAR` removed
- exact normalized name match only

Regional/variant names (`Radiant Charizard`, `Hisuian ...`) and multi-Pokémon cards are left for manual mapping. The table supports multiple Pokémon per card.

The table is a technical ETL helper; your logical analytical model can still show only the three Topic tables in the ERM.

### 3. Pokémon types

Your staging model contains `pokemon_id` + `type_url`, but not the PokeAPI `slot` field. Therefore the true primary/secondary ordering cannot be recovered. The load script stores the two type names in a deterministic alphabetical order. If `type_one`/`type_two` are supposed to mean primary/secondary type, add `slot` to staging and change the load accordingly.

### 4. Daily prices

The logical Core grain is:

`card_id + printing_type + date_id`

If staging contains two different `market_price` values for the same resolved card/printing/date, the price load fails deliberately. Run the quality-check script and fix the source data.

### 5. What is deliberately NOT calculated in Core

The following belong later in Business/Reporting:

- usage rate
- win rate
- average monthly price
- month-end price
- 1/3/12-month price change
- correlations between stats, usage and prices

Core retains the detailed counts/results, daily prices, dimensions, and integration relationships needed to calculate those values.

## Example using psql

```bash
psql -d your_dwh_database -f 00_create_core_schema.sql
psql -d your_dwh_database -f 01_staging_quality_checks.sql
psql -d your_dwh_database -f 02_load_dimensions_and_mapping.sql
# add manual mappings if necessary
psql -d your_dwh_database -f 04_load_core_support_facts.sql
psql -d your_dwh_database -f 05_load_topics.sql
psql -d your_dwh_database -f 06_validate_core.sql
```
