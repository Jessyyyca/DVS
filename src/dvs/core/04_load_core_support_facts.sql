-- 04_load_core_support_facts.sql
-- Loads CORE_DECK_RESULT and CORE_CARD_PRICE.

BEGIN;

-- ---------- CORE_DECK_RESULT ----------
INSERT INTO core.core_deck_result (deck_id, date_id, wins, losses, ties)
SELECT
    d.deck_id,
    dt.date_id,
    coalesce(d.wins, 0),
    coalesce(d.losses, 0),
    coalesce(d.ties, 0)
FROM staging.deck d
JOIN core.dim_date dt
  ON dt.full_date = coalesce(d.play_date::date, d.event_date::date)
WHERE d.deck_id IS NOT NULL
ON CONFLICT (deck_id) DO UPDATE
SET date_id = EXCLUDED.date_id,
    wins    = EXCLUDED.wins,
    losses  = EXCLUDED.losses,
    ties    = EXCLUDED.ties;

-- ---------- Guard against conflicting daily prices ----------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM staging.daily_price dp
        JOIN core.v_card_product_unique u
          ON u.product_id = dp.product_id
        GROUP BY u.card_id, dp.printing_type, dp.price_date
        HAVING count(DISTINCT dp.market_price) > 1
    ) THEN
        RAISE EXCEPTION
            'CORE_CARD_PRICE load stopped: conflicting market_price values exist for the same resolved card / printing / date. Run 01_staging_quality_checks.sql.';
    END IF;
END $$;

-- ---------- CORE_CARD_PRICE ----------
-- Only unambiguous one-to-one Limitless <-> TickerMint mappings are loaded.
-- Identical duplicate source rows are collapsed with MAX().
INSERT INTO core.core_card_price (card_id, printing_type, date_id, market_price)
SELECT
    u.card_id,
    dp.printing_type,
    dt.date_id,
    max(dp.market_price)::numeric(14,4) AS market_price
FROM staging.daily_price dp
JOIN core.v_card_product_unique u
  ON u.product_id = dp.product_id
JOIN core.dim_date dt
  ON dt.full_date = dp.price_date::date
LEFT JOIN staging.printing pr
  ON pr.product_id = dp.product_id
 AND pr.printing_type = dp.printing_type
WHERE dp.market_price IS NOT NULL
  AND dp.printing_type IS NOT NULL
GROUP BY u.card_id, dp.printing_type, dt.date_id
ON CONFLICT (card_id, printing_type, date_id) DO UPDATE
SET market_price = EXCLUDED.market_price;

COMMIT;
