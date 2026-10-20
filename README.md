# Data Warehouse zum Thema Pokemon

Im Rahmen der Projektarbeit im Modul Datenverwaltungssysteme wurde ein Data Warehouse erstellt. Dieses befasst sich mit dem Sammelkartenspiel Pokemon. Die Pokemon-Spielereihe von Nintendo und der Spielesoftwarefirma Game Freak erfreut sich seit Jahren großer Beliebtheit. In den Spielen werden die Kreaturen - als Pokemon bezeichnet - gefangen und tragen Kämpfe untereinander aus. Dabei sind ihre Eigenschaften - wie HP (Gesundheitspunkte), Attack (Angriffskraft) und Defense (Verteidigungskraft) - relevant. Des Weiteren werden die Pokemon in 18 verschiedene Typen (z.B. Feuer, Wasser, Pflanze, Gift usw.) unterteilt. Analog zu den Videospielen gibt es auch physische Sammelkarten, welche die Pokemon abbilden und ebenfalls Angriffe besitzen, um gegeneinander zu Kämpfen. So können auch mit den Sammelkarten Turniere veranstaltet werden. Des Weiteren erfreut sich das Handeln mit Pokemonkarten großer Beliebtheit. In Onlinebörsen werden regelmäßig Pokemonkarten gehandelt - diese Preise nutzen wir ebenfalls zur Analyse. Mit Hilfe des Data Warehouses sollen folgende Fragestellungen analysiert werden:

1. Vergleich der Preise von Pokemonkarten mit Eigenschaften der Pokemon
2. Vergleich der Preise von Pokemonkarten mit Verwendung in Turnieren.
3. Vergleich der Verwendung von Pokemonkarten in Turnieren mit Eigenschaften Pokemon

## 1. Fragestellung: Vergleich der Kartenpreise mit Eigenschaften der Pokemon
Das erste Analyseszenario beschäftigt sich mit den Preisen von Pokemonkarten und der Eigenschaften der darauf abgebildeten Pokemon. So kann herausgefunden werden, ob beispielsweise die Karten der Pokemon mit besonders hohen Basestats (HP, Attack, Defense) auch hohe Preise auf dem Markt erzielen oder ob bestimmte Typen besonders hochpreisig gehandelt werden.

## 2. Fragestellung: Vergleich der Kartenpreise mit der Verwendung der Karten in Turnieren
Das zweite Analyseszenario thematisiert die Verwendung von Pokemonkarten in Turnieren und untersucht, ob eine Korrelation mit ihren Kartenpreisen existiert. Die Vermutung liegt Nahe, dass Karten, die besonders erfolgreich in Kämpfen abschneiden, entsprechend höhere Preise in den Onlinebörsen erzielen - dies soll mit Hilfe des Data Warehouses überprüft werden.

Quellsysteme:
- Daten zu Pokemon: PokeAPI - https://pokeapi.co/
- Daten zu Karten-Preisen: TickerMint - https://tickermint.cards/developers
- Daten zu Turniern: Limitless - https://docs.limitlesstcg.com/developer.html

Analysedimensionen:
- Zeit
- Pokemon-Typ
- printing-Typ von Karten
- Seltenheit einer Karte

Kennzahlen:
- `usage_rate` (Verhältnis aus Decks, die die Karte beinhalten gegen die Gesamtanzahl der Decks, die in einem bestimmten Zeitraum gespielt wurden)
- `win_rate` (Verhältnis aus der Summe an Wins aller Decks, die die Karte beinhalten gegen die Gesamtzahl an Spielen aller Decks, die die Karte beinhalten)
- `adj_win_rate` (Verhältnis aus der gewichteten Summe an Wins und Ties aller Decks, die die Karte beinhalten gegen die Gesamtzahl an Spielen aller Decks, die die Karte beinhalten)
- `average_price`, `median_price`, `min_price`, `max_price` (Kennzahlen zum Preis einer Karte in einem bestimmten Zeitraum)
- Summe der base stats eines Pokemons

### Staging, Core und Reporting Layer
- Staging Layer: in [Staging-Layer.md](Staging-Layer.md) beschrieben
- Core Layer: in [Core-Layer.md](Core-Layer.md) beschrieben
- Reporting Layer: in [Reporting-Layer.md](Reporting-Layer.md) beschrieben
