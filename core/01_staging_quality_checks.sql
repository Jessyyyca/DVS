-- Read-only checks against the acquired/staging tables in public.

-- Duplicate card identity candidates.
SELECT lower(card_name) AS card_name, coalesce(set_code,''), coalesce(card_number,''), count(*)
FROM public.card
GROUP BY 1,2,3
HAVING count(*) > 1;

-- Deck-card orphans.
SELECT dc.*
FROM public.deck_card dc
LEFT JOIN public.deck d ON d.deck_id = dc.deck_id
LEFT JOIN public.card c ON c.card_id = dc.card_id
WHERE d.deck_id IS NULL OR c.card_id IS NULL;

-- Card products without a matched TickerMint product.
SELECT card_id, card_name, search_query
FROM public.card_product
WHERE product_id IS NULL;

-- More than one Limitless card linked to the same TickerMint product should not happen.
SELECT product_id, count(*)
FROM public.card_product
WHERE product_id IS NOT NULL
GROUP BY product_id
HAVING count(*) > 1;

-- Price rows without a matching card_product.
SELECT dp.*
FROM public.daily_price dp
LEFT JOIN public.card_product cp ON cp.product_id = dp.product_id
WHERE cp.product_id IS NULL;

-- Price duplicates at the intended Core grain.
SELECT cp.card_id, dp.printing_type, dp.price_date, count(*)
FROM public.daily_price dp
JOIN public.card_product cp ON cp.product_id = dp.product_id
WHERE cp.card_id IS NOT NULL
GROUP BY cp.card_id, dp.printing_type, dp.price_date
HAVING count(*) > 1;

-- Pokemon-type orphans / unresolved type URLs.
SELECT pt.*
FROM public.pokemon_type pt
LEFT JOIN public.pokemon p ON p.id = pt.pokemon_id
LEFT JOIN public.type t ON t.url_id = pt.type_url
WHERE p.id IS NULL OR t.url_id IS NULL;

-- Dates that cannot be loaded into DIM_DATE.
SELECT deck_id, event_date, play_date
FROM public.deck
WHERE coalesce(play_date, event_date) IS NULL;
