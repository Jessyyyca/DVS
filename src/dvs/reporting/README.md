# Reporting / Business layer

This folder implements the three analysis scenarios from the repository `README.md` as Reporting/Business-layer star schemas using the `core` schema as the source.

## Analysis-scenario mapping

1. **Card prices vs Pokemon type/base stats**
   - Fact: `reporting.fact_pokemon_card_price`
   - Analysis view: `reporting.v_pokemon_card_price_metrics`
   - The view contains Pokemon types and all individual/base-stat fields together with every available daily card-price observation.

2. **Card prices vs tournament usage/performance**
   - Fact: `reporting.fact_card_competitive_price`
   - Analysis view: `reporting.v_card_competitive_price_metrics`
   - The view is driven by the **daily price timeline**, not by tournament dates. Every available price observation for a card is returned. Tournament metrics are overlaid on the same date, plus rolling 7-day and 30-day usage/win-rate metrics and the most recent date on which the card was used.
   - This supports charts such as `full_date -> average_price` together with `usage_rate_30d` or `win_rate_30d`, so a later price increase can be compared with earlier competitive success.

3. **Tournament usage/performance vs Pokemon type/base stats**
   - Fact: `reporting.fact_pokemon_competitive`
   - Analysis view: `reporting.v_pokemon_competitive_metrics`
   - The view exposes type, each base stat, `base_stat_total`, usage rate, win rate and adjusted win rate by tournament date.

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

## Date dimension

`reporting.dim_date_reporting` contains:

- `full_date`
- `weekday` — ISO weekday, Monday = 1 through Sunday = 7
- `monthday` — day of month, 1 through 31
- `month`
- `quarter`
- `year`

## Price aggregation

`core.core_card_price` contains one row per Card x Printing x Date. The reporting stars require one price summary per Card x Date, so the load scripts aggregate across printings:

- `market_price` / `average_price` = average market price across printings
- `median_market_price` / `median_price` = median across printings
- `min_market_price` / `min_price` = minimum across printings
- `max_market_price` / `max_price` = maximum across printings

The same daily price aggregation is used in analysis scenarios 1 and 2.

## Why scenario 2 is price-timeline driven

A same-day-only join between card usage and price is insufficient for the project question "comparison of card prices with tournament usage" because a price reaction can happen **after** a tournament period.

`reporting.v_card_competitive_price_metrics` therefore returns every available daily price observation. On each price date it includes:

- exact-date tournament usage/performance when tournaments were observed that day;
- 7-day rolling `usage_rate_7d`, `win_rate_7d`, and `adjusted_win_rate_7d`;
- 30-day rolling `usage_rate_30d`, `win_rate_30d`, and `adjusted_win_rate_30d`;
- `last_used_date` and `days_since_last_use`;
- the price change from the previous available price observation.

A day with no tournament observation is represented with `has_tournament_observation = false`; it is **not** interpreted as zero tournament usage. A tournament day on which the card was not used has `has_tournament_observation = true` and `decks_using_card = 0`.

## Monthly price metrics

`reporting.v_card_monthly_price_metrics` provides:

- `average_month_price`
- `median_month_price`
- `min_month_price`
- `max_month_price`
- `month_end_price`
- 1/3/12-month absolute and percentage price changes

## Competitive facts

`total_decks` is calculated independently per Core date from all rows in `core.core_deck_result`.

For a specific Pokemon/Card and date, `decks_using_*`, copy counts, wins, losses and ties are derived from the corresponding Core topic table joined to `core.core_deck_result`.

Rates such as `usage_rate` and `win_rate` are intentionally not stored as facts because they are non-additive. `05_create_metric_views.sql` derives them when queried.

`win_rate` is stored as a ratio from 0 to 1, e.g. 6 wins and 0 losses/ties = `1.0` = 100%.

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
