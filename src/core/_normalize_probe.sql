-- Standalone probe for the new normalization chain in
-- 02_load_dimensions_and_mapping.sql. Drop-in test: runs against any
-- Postgres without needing the staging tables. Paste the output back into
-- the PR when reviewing whether the regex needs further tuning.
--
-- Run:
--   psql "$DVS_DB_DSN" -f src/core/_normalize_probe.sql

WITH samples(name) AS (
    VALUES
        -- Should resolve to a Pokemon after the chain.
        ('N''s Vanillite'),
        ('N''s Vanillish'),
        ('N''s Sigilyph'),
        ('Cynthia''s Gible'),
        ('Cynthia''s Gabite'),
        ('Cynthia''s Garchomp ex'),
        ('Steven''s Baltoy'),
        ('Steven''s Claydol'),
        ('Iono''s Wattrel'),
        ('Iono''s Kilowattrel'),
        ('Team Rocket''s Moltres ex'),
        ('Team Rocket''s Wobbuffet'),
        ('Morty''s Conviction'),
        ('N''s Plan'),
        ('Ethan''s Ho-Oh ex'),
        ('Mega Gengar ex'),
        ('Mega Lopunny ex'),
        ('Mega Latias ex'),
        ('Mega Froslass ex'),
        ('Charizard ex'),
        ('Pikachu VMAX'),
        ('Mamoswine ex'),
        ('Lugia ex'),
        ('Sinistcha ex'),
        ('Miraidon ex'),
        ('Salazzle ex'),
        ('Ninetales ex'),
        ('Milotic ex'),
        ('Cynthia''s Roselia'),
        -- Should remain unmapped (trainer / item / energy / location).
        ('Cheren'),
        ('Friends in Paldea'),
        ('Levincia'),
        ('Boss''s Orders'),
        ('Poké Ball'),
        ('Switch'),
        ('Community Center'),
        ('Lively Stadium'),
        ('Academy at Night'),
        ('Perilous Jungle'),
        ('Tera Orb'),
        ('Antique Plume Fossil'),
        ('Antique Root Fossil'),
        ('Growing Grass Energy'),
        ('Survival Brace'),
        ('Fighting Au Lait'),
        ('Blowtorch'),
        ('Deluxe Bomb'),
        ('Thick Scale'),
        ('Passimian'),
        ('Applin'),
        ('Chi-Yu'),
        ('Miraidon'),
        ('Uxie'),
        ('Drapion'),
        ('Kyurem'),
        ('Hydreigon ex'),
        ('Cobalion ex'),
        ('Munkidori ex'),
        ('Okidogi ex'),
        ('Zarude'),
        ('Enamorus'),
        ('Annihilape'),
        ('Slowpoke'),
        ('Slowking'),
        ('Applin'),
        ('Dipplin'),
        ('Crocalor'),
        ('Glimmora'),
        ('Feebas'),
        ('Electrike'),
        ('Relicanth'),
        ('Yamask'),
        ('Cofagrigus'),
        ('Togepi'),
        ('Togekiss'),
        ('Phione'),
        ('Petilil'),
        ('Lilligant'),
        ('Swinub'),
        ('Piloswine'),
        ('Buneary'),
        ('Shroomish'),
        ('Flittle'),
        ('Vulpix'),
        ('Clefairy'),
        ('Heatran'),
        ('Steven''s Baltoy'),
        ('Steven''s Claydol'),
        ('Magmar'),
        ('Magmortar'),
        ('Salandit'),
        ('Turtonator'),
        ('Latios'),
        ('Skorupi'),
        ('Antique Plume Fossil'),
        ('Antique Root Fossil'),
        ('Fighting Au Lait'),
        ('Mega Gengar ex'),
        ('Mega Lopunny ex'),
        ('Mega Latias ex'),
        ('Mega Froslass ex'),
        ('Lunala Prism Star'),
        ('Charizard Prerelease Promo'),
        ('Ancient Mew M')
), cleaned AS (
    SELECT name, lower(name) AS raw_name FROM samples
), step_owner AS (
    SELECT name, regexp_replace(raw_name, '^\s*[a-z0-9]{1,20}\x27\s*\s*', '', 'i') AS n1 FROM cleaned
), step_mega AS (
    SELECT name, regexp_replace(n1, '^mega\s+', '', 'i') AS n2 FROM step_owner
), step_suffix AS (
    SELECT name,
           regexp_replace(
               regexp_replace(
                   regexp_replace(
                       regexp_replace(
                           regexp_replace(
                               regexp_replace(
                                   regexp_replace(
                                       regexp_replace(n2,
                                           '\s+(prerelease promo|staff promo|league promo|prelease promo)\s*$', '', 'i'),
                                       '\s+(tag team|delta species|spirit link|prism star|v-union|v-double)\s*$', '', 'i'),
                                   '\s+(radiant|legend|spiral|vstar|vmax|gx|break|prime|baby)\s*$', '', 'i'),
                               '\s+(ex|v)\s*$', '', 'i'),
                           '\s+(lv\.?x)\s*$', '', 'i'),
                       '\s+(promo|legend)\s*$', '', 'i'),
                   '\s+(star)\s*$', '', 'i'),
               '\s+m\s*$', '', 'i') AS n3
    FROM step_mega
), step_alphanum AS (
    SELECT name, trim(regexp_replace(n3, '[^a-z0-9]+', ' ', 'g')) AS n4 FROM step_suffix
)
SELECT name AS original,
       n4 AS normalized,
       regexp_replace(n4, '^(hisuian|galarian|alolan|paldean|unovan|kalosian|original)\s+', '', 'i') AS regional_stripped
FROM step_alphanum
ORDER BY name;
