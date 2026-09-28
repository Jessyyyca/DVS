# Reporting / Business layer

This folder implements the three star schemas documented in `Star_Schemas_Reporting.md` using the `core` schema as the source.

## Objects

Shared conformed dimensions:

- `reporting.dim_date_reporting`
- `reporting.dim_pokemon_reporting`
- `reporting.dim_card_reporting`

Facts:

- `reporting.fact_pokemon_competitive` — grain: Pokemon x Date
- `reporting.fact_card_competitive_price` — grain: Card x Date
- `reporting.fact_pokemon_card_price` — grain: Pokemon x Card x Date

The Reporting layer uses surrogate keys (`pokemon_key`, `card_key`, `date_key`). Core IDs remain as unique natural-key attributes in the dimensions.

## Price aggregation

`core.core_card_price` contains one row per Card x Printing x Date. The reporting stars require one price per Card x Date, so the load scripts aggregate across printings:

- `market_price` = average market price across printings
- `min_market_price` = minimum market price across printings
- `max_market_price` = maximum market price across printings

This rule is used consistently in Star 2 and Star 3.

## Competitive facts

`total_decks` is calculated independently per Core date from all rows in `core.core_deck_result`.

For a specific Pokemon/Card and date, `decks_using_*`, copy counts, wins, losses and ties are derived from the corresponding Core topic table joined to `core.core_deck_result`.

Rates such as `usage_rate` and `win_rate` are intentionally not stored as facts because they are non-additive. `05_create_metric_views.sql` derives them when queried.

## Card set name

`Star_Schemas_Reporting.md` includes `set_name` in `DIM_CARD_REPORTING`, but the current `core.dim_card` contains only `card_id`, `card_name`, and `rarity`. To keep the architectural direction `Core -> Reporting`, `set_name` is currently created but left `NULL` rather than reading the staging/source schema directly. If a set attribute is later added to Core, `01_load_dimensions.sql` can populate it without changing the star-schema grain.

## Load order

Run the scripts in this order:

```text
00_create_reporting_schema.sql
01_load_dimensions.sql
02_load_fact_pokemon_competitive.sql
03_load_fact_card_competitive_price.sql
04_load_fact_pokemon_card_price.sql
05_create_metric_views.sql
06_validate_reporting.sql
```

With `psql`, `07_reload_reporting.sql` executes the full sequence:

```sh
cd src/dvs/reporting
psql "$DVS_DB_DSN" -v ON_ERROR_STOP=1 -f 07_reload_reporting.sql
```

The fact-load scripts truncate and rebuild only their own fact tables. Dimension loads use upserts and therefore preserve already assigned surrogate keys.

## Derived metric views

`reporting.v_pokemon_competitive_metrics` provides `usage_rate`, `win_rate`, `adjusted_win_rate`, and `average_copies_when_used` together with Pokemon/date attributes.

`reporting.v_card_competitive_price_metrics` provides the same competitive rates plus daily card-price values.

`reporting.v_card_monthly_price_metrics` derives `average_month_price`, `month_end_price`, and 1/3/12-month price changes. The un-suffixed `price_change_*` columns are absolute price changes; corresponding `*_pct` columns contain relative changes.

## Sparse fact behavior

`fact_pokemon_competitive` contains rows for Pokemon/date combinations where the Pokemon was actually used. It does not create a full Pokemon x all tournament dates Cartesian product.

`fact_card_competitive_price` contains a row when either competitive usage or a price observation exists for a Card x Date. This allows price-only observations to remain available for analysis; their competitive measures are zero.
