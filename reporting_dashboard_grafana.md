# Reporting mit Grafana – Pokémon Competitive Play

**Dashboard:** (https://dhw_grafana.inu-the-bot.com/d/pokemon-competitive-recovery/pokemons-und-competitive-play-e28094-recovery?from=2025-03-11T23:00:00.000Z&to=2026-09-14T22:00:00.000Z&timezone=browser&var-pokemon_type=$__all&var-pokemon=$__all&var-orientation=default&var-drill_across_metric=win_rate&var-granularity=week&var-min_bst=0&var-max_bst=999))

## Ziel und Datengrundlage

Das Dashboard untersucht die Nutzung und den Erfolg von Pokémon im kompetitiven Pokémon-Kartenspiel im Vergleich zu Eigenschaften aus den Videospielen. Im Mittelpunkt stehen die **Usage-Rate** (Anteil der Decks, in denen ein Pokémon verwendet wird) und die **Win-Rate** (Anteil gewonnener Partien).
Als Grundlage dient das bereits im Gesamtprojekt erstellte PostgreSQL-Data-Warehouse.

## Anbindung und Darstellung in Grafana

Die Datenbank wurde in Grafana über **Connections → Data sources** als PostgreSQL-Datenquelle `grafana-postgresql-datasource` eingerichtet und als Standard festgelegt. Die Verbindung verwendet den Host `postgres-dhw`, die Datenbank `db` und den Datenbankbenutzer `dhw` (Authentifizierung per hinterlegtem Passwort). Die Abfragen greifen auf die vorhandene View `reporting.v_pokemon_competitive_metrics` zu. Diese stellt Pokémon-Merkmale, Datumsangaben sowie Turnierkennzahlen gemeinsam für das Reporting bereit.

Die Diagramme basieren auf SQL-Abfragen in Grafana. Die Win-Rate wird aus `wins / (wins + losses + ties) × 100` berechnet; die Usage-Rate aus `decks_using_pokemon / total_decks × 100`. Dafür werden zunächst die jeweiligen Zähler und Nenner über den gewählten Auswertungsbereich summiert.

Das Dashboard enthält folgende Darstellungen:

- **Win-Rate over Time:** zeitlicher Verlauf der Gewinnquoten ausgewählter Pokémon.
- **Usage-Rate over Time:** zeitlicher Verlauf ihrer Nutzungsquoten.
- **Pokémon Performance:** XY-Streudiagramm zum Vergleich von Usage-Rate (X-Achse) und Win-Rate (Y-Achse). Mit *Orientation* lässt sich die Achsenbelegung umkehren.
- **Pokémon × Time – Performance Matrix:** Tabelle mit Pokémon und Zeitperioden als Dimensionen. Die Zellen zeigen je nach Auswahl Win-Rate oder Usage-Rate in Prozent.

Über die Auswahl **Drill measure** (`win_rate` oder `usage_rate`) wird die betrachtete Kennzahl gewechselt. Entsprechend wird eines der beiden Zeitreihendiagramme eingeblendet und die Matrix übernimmt die gewählte Kennzahl.

## Umsetzung der OLAP-Funktionen

Die OLAP-Funktionen werden über die Dashboard-Auswahlfelder und die dazugehörigen SQL-Abfragen umgesetzt:

| Funktion | Umsetzung im Dashboard | Beispiel |
|---|---|---|
| **Slice** | Ein Wert einer Dimension wird über den Filter **Pokemon Type** oder **Pokemon** ausgewählt. | Nur Pokémon vom Typ *Fire* auswählen und deren Win-Rates betrachten. |
| **Dice** | Mehrere Dimensionen werden gleichzeitig eingeschränkt: **Pokemon Type**, **Pokemon** und der Grafana-Zeitraumfilter. | Zwei Pokémon-Typen auswählen und die Ergebnisse auf einen bestimmten Zeitraum begrenzen. |
| **Drilldown / Roll-up** | Mit **Date granularity** wird die zeitliche Gruppierung der Daten gesteuert (`year`, `quarter`, `month`, `week`, `day`). Die SQL-Abfragen verwenden hierfür `DATE_TRUNC`. | Von einer Jahresübersicht zur Monats- oder Wochenansicht wechseln, um Veränderungen genauer zu untersuchen. Anschließend kann man zurück zur Jahresaggregation wechseln. |
| **Pivot** | **Orientation** (`default`/`reversed`) vertauscht in der Performance-Matrix die Zeilen- und Spaltendimensionen Pokémon und Zeitraum. Im Streudiagramm wechselt zugleich die Zuordnung von Win-Rate und Usage-Rate zu den Achsen. | Statt „Pokémon als Zeilen, Monate als Spalten“ die Monate als Zeilen und Pokémon als Spalten ansehen. |

Zusätzlich unterstützt **Drill measure** einen **Kennzahlenwechsel (Drill-across)** zwischen Win-Rate und Usage-Rate. Dadurch kann dieselbe Auswahl an Pokémon und Zeitperioden anhand unterschiedlicher Kennzahlen verglichen werden. Dies ist vom zeitlichen Drilldown zu unterscheiden: Beim Drilldown ändert sich die **Detailtiefe**, beim Kennzahlenwechsel die **betrachtete Messgröße**.
