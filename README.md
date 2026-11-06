# Data Warehouse zum Thema Pokemon

Im Rahmen der Projektarbeit im Modul Datenverwaltungssysteme wurde ein Data Warehouse erstellt. Dieses befasst sich mit dem Sammelkartenspiel Pokemon. Die Pokemon-Spielereihe von Nintendo und der Spielesoftwarefirma Game Freak erfreut sich seit Jahren großer Beliebtheit. In den Spielen werden die Kreaturen - als Pokemon bezeichnet - gefangen und tragen Kämpfe untereinander aus. Dabei sind ihre Eigenschaften - wie HP (Gesundheitspunkte), Attack (Angriffskraft) und Defense (Verteidigungskraft) - relevant. Des Weiteren werden die Pokemon in 18 verschiedene Typen (z.B. Feuer, Wasser, Pflanze, Gift usw.) unterteilt. Analog zu den Videospielen gibt es auch physische Sammelkarten, welche die Pokemon abbilden und ebenfalls Angriffe besitzen, um gegeneinander zu Kämpfen. So können auch mit den Sammelkarten Turniere veranstaltet werden, indem Decks - jeweils bestehend aus 60 Karten - gegeneinander antreten. Des Weiteren erfreut sich das Handeln mit Pokemonkarten großer Beliebtheit. In Onlinebörsen werden regelmäßig Pokemonkarten gehandelt - diese Preise nutzen wir ebenfalls zur Analyse. Mit Hilfe des Data Warehouses sollen folgende Fragestellungen analysiert werden:

1. Vergleich der Preise von Pokemonkarten mit Eigenschaften der Pokemon
2. Vergleich der Preise von Pokemonkarten mit Verwendung in Turnieren.
3. Vergleich der Verwendung von Pokemonkarten in Turnieren mit Eigenschaften Pokemon

## 1. Fragestellung: Vergleich der Kartenpreise mit Eigenschaften der Pokemon
Das erste Analyseszenario beschäftigt sich mit den Preisen von Pokemonkarten und der Eigenschaften der darauf abgebildeten Pokemon. So kann herausgefunden werden, ob beispielsweise die Karten der Pokemon mit besonders hohen Basestats (HP, Attack, Defense) auch hohe Preise auf dem Markt erzielen oder ob bestimmte Typen besonders hochpreisig gehandelt werden.

## 2. Fragestellung: Vergleich der Kartenpreise mit der Verwendung der Karten in Turnieren
Das zweite Analyseszenario thematisiert die Verwendung von Pokemonkarten in Turnieren und untersucht, ob eine Korrelation mit ihren Kartenpreisen existiert. Die Vermutung liegt Nahe, dass Karten, die besonders erfolgreich in Kämpfen abschneiden, entsprechend höhere Preise in den Onlinebörsen erzielen - dies soll mit Hilfe des Data Warehouses überprüft werden.

## 3. Fragestellung: Vergleich der Pokemon-Eigenschaften mit Verwendung der Karten in Turnieren
Das dritte Analyseszenario untersucht, inwiefern sich die Eigenschaften von Pokemon (HP, Attack, Type) auf die Verwendung der zugehörigen Pokemonkarten in den Turnieren und deren Erfolg auswirken. So wäre eine interessante Frage, welcher Pokemon-Typ am häufigsten in Turnieren genutzt wird und ob dieser Typ auch die besten Ergebnisse (in Hinblick auf die winrate) erziehlt.

## Quellsysteme:
Zur Beantwortung der Fragen wurden folgende Quellsysteme genutzt:
- Daten zu Pokemon: PokeAPI - https://pokeapi.co/
- Daten zu Karten-Preisen: TickerMint - https://tickermint.cards/developers
- Daten zu Turniern: Limitless - https://docs.limitlesstcg.com/developer.html
Die PokeAPI stellt alle Daten rund um die Eigenschaften der Pokemon zur Verfügung, die zur Beantwortung der 1. und 3. Fragestellung notwendig sind. So werden jedem Pokemon ihre Basestats und 1-2 Typen zugeordnet.
Tickermint bietet eine Übersicht über die täglichen Preise der Pokemon-Karten, die im Online-Handel erziehlt werden, sowie Informationen zur Ausführung der Karten (diese können mit einer Holofolie versehen sein, was im Allgemeinen den Wert steigert).
Zuletzt versorgt uns Limitless mit Daten zu Turnieren - welche Pokemonkarten in einem Deck genutzt und wie viele Spiele mit diesem Deck gespielt und davon gewonnen, verloren oder mit einem einen Unentschieden abgeschlossen wurden.  

## Analysedimensionen:
Die folgenden Analysedimensionen werden im Data Warehouse betrachtet:
- Zeit
- Pokemon-Typ
- printing-Typ von Karten
- Seltenheit einer Karte

## Kennzahlen:
Die relevanten Kennzahlen umfassen:
- `usage_rate` (Verhältnis aus Decks, die die Karte beinhalten gegen die Gesamtanzahl der Decks, die in einem bestimmten Zeitraum gespielt wurden)
- `win_rate` (Verhältnis aus der Summe an Wins aller Decks, die die Karte beinhalten gegen die Gesamtzahl an Spielen aller Decks, die die Karte beinhalten)
- `adj_win_rate` (Verhältnis aus der gewichteten Summe an Wins und Ties aller Decks, die die Karte beinhalten gegen die Gesamtzahl an Spielen aller Decks, die die Karte beinhalten)
- `average_price`, `median_price`, `min_price`, `max_price` (Kennzahlen zum Preis einer Karte in einem bestimmten Zeitraum)
- Summe der Basestats eines Pokemons

## Die einzelnen Kapitel:
Informationen zu den einzelnen Kapiteln finden sich hier:
- Staging Layer: in [Staging-Layer.md](Staging-Layer.md) beschrieben
- Core Layer: in [Core-Layer.md](Core-Layer.md) beschrieben
- Reporting Layer: in [Reporting-Layer.md](Reporting-Layer.md) beschrieben
- Machine Learning: in [Machine-Learning.md](Machine-Learning.md) beschrieben
- No-SQL: in [No-SQL.md](No-SQL.md) beschrieben
