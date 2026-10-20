# DVS

Fragestellungen:
1. Vergleich der Preise von Pokemonkarten mit Typ und Basestats aus Pokemonspielen
2. Vergleich der Preise von Pokemonkarten mit Verwendung in Turnieren.
3. Vergleich der Verwendung in Turnieren mit Typ und Basestats aus Pokemonspielen

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
