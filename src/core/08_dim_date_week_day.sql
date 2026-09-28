-- 08_dim_date_week_day.sql
-- One-off migration for core.dim_date:
--   * rename the existing day-of-month column "day" to "month_day"
--   * add a true day-of-week column "week_day"
--     (ISO 8601: 1 = Monday … 7 = Sunday)
--
-- Why both columns:
--   The original "day" column stores day-of-month (1..31), which is genuinely
--   useful for reporting (e.g. "every 15th of the month") but ambiguous as
--   a name. "month_day" makes the meaning explicit. "week_day" is the ISO
--   day-of-week most BI tools expect (Mon=1..Sun=7).
--
-- After this script, the loader in 02_load_dimensions_and_mapping.sql and
-- the row count in 06_validate_core.sql MUST be updated to write
-- "month_day" + "week_day" instead of "day" -- otherwise every reload
-- will fail with "column 'day' does not exist".
--
-- Re-runnable: every ALTER below uses IF EXISTS / IF NOT EXISTS guards.

BEGIN;

-- 1) Rename day -> month_day. Done first so the new columns line up with the
--    order in 00_create_core_schema.sql.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'core'
          AND table_name   = 'dim_date'
          AND column_name  = 'day'
    ) AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'core'
          AND table_name   = 'dim_date'
          AND column_name  = 'month_day'
    ) THEN
        ALTER TABLE core.dim_date
            RENAME COLUMN day TO month_day;
    END IF;
END$$;

-- 2) Add week_day as a nullable column first so the ALTER on a populated
--    table does not require a single-statement DEFAULT.
ALTER TABLE core.dim_date
    ADD COLUMN IF NOT EXISTS week_day INT;

-- 3) Backfill from full_date. ISODOW gives 1..7 (Monday..Sunday), which
--    is what most BI tools expect for "week day".
UPDATE core.dim_date
SET week_day = EXTRACT(ISODOW FROM full_date)::int
WHERE week_day IS NULL;

-- 4) Promote to NOT NULL once every row has a value. CHECK keeps it sane.
ALTER TABLE core.dim_date
    ALTER COLUMN week_day SET NOT NULL;

ALTER TABLE core.dim_date
    DROP CONSTRAINT IF EXISTS dim_date_week_day_range;

ALTER TABLE core.dim_date
    ADD CONSTRAINT dim_date_week_day_range
    CHECK (week_day BETWEEN 1 AND 7);

-- 5) Add an explicit CHECK on month_day too -- protects against bad
--    backfills (e.g. EXTRACT(DAY) on an out-of-range date).
ALTER TABLE core.dim_date
    DROP CONSTRAINT IF EXISTS dim_date_month_day_range;

ALTER TABLE core.dim_date
    ADD CONSTRAINT dim_date_month_day_range
    CHECK (month_day BETWEEN 1 AND 31);

COMMIT;

-- Verify the final shape.
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'core'
  AND table_name = 'dim_date'
ORDER BY ordinal_position;