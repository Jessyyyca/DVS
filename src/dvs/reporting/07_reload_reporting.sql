-- 07_reload_reporting.sql
-- Convenience runner for psql. Run from this directory with:
--   psql "$DVS_DB_DSN" -v ON_ERROR_STOP=1 -f 07_reload_reporting.sql

\set ON_ERROR_STOP on

\ir 00_create_reporting_schema.sql
\ir 01_load_dimensions.sql
\ir 02_load_fact_pokemon_competitive.sql
\ir 03_load_fact_card_competitive_price.sql
\ir 04_load_fact_pokemon_card_price.sql
\ir 05_create_metric_views.sql
\ir 06_validate_reporting.sql
