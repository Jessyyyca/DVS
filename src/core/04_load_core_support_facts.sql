BEGIN;

INSERT INTO core.core_deck_result(deck_id, date_id, wins, losses, ties)
SELECT d.deck_id,
       to_char(coalesce(d.play_date, d.event_date), 'YYYYMMDD')::int AS date_id,
       coalesce(d.wins, 0),
       coalesce(d.losses, 0),
       coalesce(d.ties, 0)
FROM public.deck d
WHERE coalesce(d.play_date, d.event_date) IS NOT NULL
ON CONFLICT (deck_id) DO UPDATE SET
    date_id = excluded.date_id,
    wins = excluded.wins,
    losses = excluded.losses,
    ties = excluded.ties;

INSERT INTO core.core_card_price(card_id, printing_type, date_id, market_price)
SELECT cp.card_id,
       dp.printing_type,
       to_char(dp.price_date, 'YYYYMMDD')::int AS date_id,
       dp.market_price
FROM public.daily_price dp
JOIN public.card_product cp ON cp.product_id = dp.product_id
JOIN core.dim_card c ON c.card_id = cp.card_id
WHERE cp.card_id IS NOT NULL
ON CONFLICT (card_id, printing_type, date_id) DO UPDATE SET
    market_price = excluded.market_price;

COMMIT;
