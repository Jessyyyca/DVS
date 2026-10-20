# Core-Layer

## 1. Einordnung in die Data-Warehouse-Architektur

Der **Core-Layer** bildet die verbindende, fachlich aufbereitete Schicht zwischen den quellsystemnahen Staging-Daten und den analyseorientierten Star-Schemas im Reporting.

**Zweck des Core-Layers:** Informationen aus verschiedenen Quellsystemen verknüpfen, einheitlich beschreiben und in einer wiederverwendbaren, prüfbaren Form bereitstellen.

In diesem Projekt treffen drei fachliche Bereiche aufeinander:

- **Pokémon-Stammdaten:** Basiswerte und Typen eines Pokémon.
- **Competitive-Daten:** Decks, darin enthaltene Karten und Ergebnisse (Siege, Niederlagen, Unentschieden).
- **Karten- und Preisdaten:** Sammelkarten, deren Varianten (`printing_type`) und zeitbezogene Marktpreise.

Damit können drei Fragestellungen beantwortet werden:

1. Besteht ein Zusammenhang zwischen den **Basiswerten eines Pokémon** und seiner **Nutzung beziehungsweise Performance in Competitive-Decks**?
2. Besteht ein Zusammenhang zwischen dem **Marktpreis einer Sammelkarte** und ihrer **Nutzung beziehungsweise Performance im Competitive-Bereich**?
3. Besteht ein Zusammenhang zwischen den **Basiswerten eines Pokémon** und den **Marktpreisen der ihm zugeordneten Sammelkarten**?

Die einzelnen Datenbereiche dürfen nicht allein über ähnlich aussehende Namen verbunden werden: Ein Pokémon ist eine Spielfigur beziehungsweise Spezies, eine Sammelkarte ist ein eigenes Objekt. Ein Pokémon kann mehreren Karten zugeordnet sein.

## 2. Modellierungsansatz: Topic-, Core- und Dimensionstabellen

Die Aufgabenstellung sieht **je Fragestellung eine Topic-Tabelle** sowie die benötigten Dimensionen im Core vor. In unserem Entwurf gibt es deshalb drei Topic-Tabellen. Zusätzlich werden zwei fachlich gemeinsam genutzte Core-Tabellen eingerichtet. Letztere sind eine **projektspezifische Erweiterung** der Mindeststruktur aus der Aufgabenstellung.

- **Topic-Tabellen** stellen genau die Beziehungen bereit, die eine Analyse benötigt, und definieren die entsprechende Granularität.
- **Gemeinsame Core-Tabellen** speichern Sachverhalte, die mehrere Analysen verwenden, einmal an zentraler Stelle. Diese Aufteilung reduziert redundante Datenhaltung und widersprüchliche Berechnungsgrundlagen; eine bessere Abfrageperformance ist möglich, aber nicht automatisch gewährleistet.
- **Dimensionstabellen** liefern einheitlich benannte, beschreibende Merkmale, entlang derer im Reporting gefiltert und gruppiert wird.


## 2.1 Entity-Relationship-Diagramm der Core-Schicht

Das folgende Diagramm zeigt die Beziehungen zwischen den drei Topic-Tabellen, den gemeinsam genutzten Core-Tabellen und den Dimensionstabellen.

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryTextColor": "#171717", "textColor": "#171717", "lineColor": "#444444", "primaryBorderColor": "#555555", "background": "#ffffff"}}}%%
erDiagram
    core.dim_pokemon {
        int pokemon_id PK
        string pokemon_name
        int hp
        int attack
        int defense
        int special_attack
        int special_defense
        int speed
        string type_one
        string type_two
    }
    core.dim_date {
        int date_id PK
        date full_date
        int day
        int month
        int quarter
        int year
    }
    core.dim_card {
        int card_id PK
        string card_name
        string set_name
        string rarity
    }
    core.core_deck_result {
        string deck_id PK
        int date_id FK
        int wins
        int losses
        int ties
    }
    core.core_card_price {
        int card_id PK,FK
        string printing_type PK
        int date_id PK,FK
        decimal market_price
    }
    core.topic_base_stats_vs_competitive {
        string deck_id PK,FK
        int pokemon_id PK,FK
        int pokemon_copy_count
    }
    core.topic_pokemon_price {
        int pokemon_id PK,FK
        int card_id PK,FK
    }
    core.topic_card_competitive {
        string deck_id PK,FK
        int card_id PK,FK
        int card_copy_count
    }

    core.dim_date ||--o{ core.core_deck_result : played_on
    core.dim_date ||--o{ core.core_card_price : observed_on
    core.dim_pokemon ||--o{ core.topic_base_stats_vs_competitive : used_pokemon
    core.dim_pokemon ||--o{ core.topic_pokemon_price : pokemon
    core.dim_card ||--o{ core.topic_pokemon_price : pokemon_card
    core.dim_card ||--o{ core.topic_card_competitive : used_card
    core.dim_card ||--o{ core.core_card_price : priced
    core.core_deck_result ||--o{ core.topic_base_stats_vs_competitive : contains
    core.core_deck_result ||--o{ core.topic_card_competitive : contains

    style core.dim_pokemon fill:#EAFBF5,stroke:#009F8C,color:#171717,stroke-width:2px
    style core.dim_date fill:#FAEBFF,stroke:#BE42DE,color:#171717,stroke-width:2px
    style core.dim_card fill:#FFF2E6,stroke:#E67714,color:#171717,stroke-width:2px
    style core.core_deck_result fill:#E5F9FC,stroke:#009DBB,color:#171717,stroke-width:2px
    style core.core_card_price fill:#E9FAEF,stroke:#13AB4E,color:#171717,stroke-width:2px
    style core.topic_base_stats_vs_competitive fill:#F1EAFF,stroke:#8655D8,color:#171717,stroke-width:2px
    style core.topic_pokemon_price fill:#FFF9DF,stroke:#C79100,color:#171717,stroke-width:2px
    style core.topic_card_competitive fill:#FFEBEF,stroke:#DA4C61,color:#171717,stroke-width:2px
```

### 3.2 Topic-Tabelle: `core.topic_base_stats_vs_competitive`
**Fachlicher Zweck:** Ein Deck mit dem Pokémon verknüpfen, dessen Competitive-Nutzung analysiert werden soll.

**Granularität:** Genau eine Zeile je Kombination aus **Deck und Pokémon**. `pokemon_copy_count` bezeichnet die Anzahl der im Deck enthaltenen Kartenkopien, die diesem Pokémon zugeordnet wurden.

**Verwendung:** Die Reporting-Schicht kann je Pokémon und Beobachtungstag die Zahl der nutzenden Decks, die Kopienzahl sowie die Resultate der nutzenden Decks berechnen und diese mit den Basiswerten vergleichen.

**Wichtige Modellregel:** Falls mehrere Karten desselben Pokémon in einem Deck liegen, müssen diese auf die *eine* Zeile `deck_id + pokemon_id` zusammengeführt werden. Andernfalls führen spätere Joins zu Mehrfachzählungen der Deck-Ergebnisse.

### 3.3 Topic-Tabelle: `core.topic_pokemon_price`
**Fachlicher Zweck:** Explizite Zuordnung einer konkreten Sammelkarte zu dem Pokémon, das durch die Karte repräsentiert wird.

**Granularität:** Eine Zeile je gültiger Kombination **Pokémon × Karte**. Ein Pokemon kann zu mehreren Karten gehören.

**Verwendung:** Die Zuordnung wird für die dritte Fragestellung verwendet und kann außerdem die Pokémon-bezogene Ableitung aus der Kartenverwendung unterstützen.

**Qualitätssicherung:** Die Zuordnung wird anhand eines Namens-Matchings hergestellt. Schreibweisen und Zusätze wie `ex`, `V`, `Lv.99` oder vorangestellte Trainerbezeichnungen erfordern besondere Regeln.

### 3.4 Topic-Tabelle: `core.topic_card_competitive`

**Fachlicher Zweck:** Die Nutzung einer **konkreten Karte** in einem Competitive-Deck abbilden. Im Unterschied zur Pokémon-bezogenen Topic-Tabelle bleibt hier die `card_id` erhalten; verschiedene Karten desselben Pokémon sind somit getrennt analysierbar.

**Granularität:** Eine Zeile je Kombination aus **Deck und Karte**. `card_copy_count` zählt die Anzahl dieser Karte im Deck.

**Verwendung:** Daraus entstehen die Kennzahlen Kartenverwendung, Kopienzahl und – über die Deck-Ergebnisse – die Performance der Decks, die die jeweilige Karte verwenden.

### 3.5 Wiederverwendbare Tabelle: `core.core_deck_result`

**Fachlicher Zweck:** Einmalige, einheitliche Ablage des ausgewerteten Ergebnisses eines Decks. Sowohl die Pokémon- als auch die Kartenanalyse benötigen dieselben Competitive-Ergebnisse.

**Granularität des vorliegenden Entwurfs:** Eine Zeile pro `deck_id` mit genau einem zugeordneten `date_id`.

**Wichtige Auswertungsregel:** Nach einem Join mit einer Topic-Tabelle zählen die Ergebnisse eines Decks zu jeder darin vertretenen Pokémon- oder Kartenkategorie. Das ist für die Frage „Wie schneiden Decks ab, die X enthalten?“ sinnvoll.

### 3.6 Wiederverwendbare Tabelle: `core.core_card_price`
**Fachlicher Zweck:** Historische Marktpreise für konkrete Karten und Druckvarianten bereitstellen. Die Varianten-Information bleibt bewusst erhalten, damit die Reporting-Schicht je nach Fragestellung Durchschnitt, Minimum, Maximum oder eine bestimmte Variante auswerten kann.

**Granularität:** Eine Zeile pro **Karte × Druckvariante × Datum**. Der zusammengesetzte Primärschlüssel verhindert doppelte Preiswerte für dieselbe Kombination.

**Fachliche Abgrenzung:** Es handelt sich um Preisbeobachtungen, nicht um Verkäufe oder Umsätze. Ein Durchschnitt über Varianten bedeutet „durchschnittlicher Preis der beobachteten Varianten“, nicht durchschnittlicher tatsächlich erzielter Verkaufspreis. Fehlende Variantenpreise und ungleiche Beobachtungszahlen können diesen Mittelwert beeinflussen.

## 4. Dimensionstabellen des Core-Layers

### 4.1 `core.dim_pokemon`

**Zweck:** Beschreibende und analytisch relevante Merkmale jedes Pokémon zentral bereitstellen. Die sechs Basiswerte sind Vergleichsmerkmale der ersten und dritten Fragestellung. `type_one` und `type_two` ermöglichen die Analyse nach Typkombinationen.

Die Typinformationen entstehen aus den Staging-Tabellen `P_type` und `P_pokemon_type`. Da Typen in der Quelle über Beziehungen modelliert sein können, werden sie in zwei berichtstaugliche Attribute überführt. Pokémon ohne zweiten Typ behalten dort `NULL`.

### 4.2 `core.dim_date`
**Zweck:** Zeitinformationen über unterschiedliche Datenquellen und Sachverhalte einheitlich bereitstellen. Über dieselbe Datumsdimension lassen sich Deck-Ergebnisse und Preisbeobachtungen zeitlich einordnen, nach Wochentagen gruppieren oder Monatsvergleiche bilden.

`date_id` fungiert im Core als stabiler Datumsbezug; `full_date` enthält das Datum selbst. Für das Reporting können zusätzliche Attribute wie Quartal und Tagesnummer ergänzt werden. Beobachtungstag, Wettbewerbstag und Preisstichtag sind fachlich nicht automatisch identisch, die Bedeutung des Datums muss also dokumentiert werden.

### 4.3 `core.dim_card`
**Zweck:** Karten anhand einer stabilen Kartenidentität beschreiben und nach Namen sowie Seltenheit untersuchen. Durch die zentrale Dimension werden Kartenbezeichnungen nicht in jeder Topic- und Preistabelle redundant gespeichert.

Im Reporting-Entwurf wird zusätzlich `set_name` verwendet. Dieses Feld ist in der hier dokumentierten Core-Dimension bisher **nicht enthalten**. Seine Herkunft aus dem Staging muss geklärt und der Core gegebenenfalls entsprechend erweitert werden. `card_id` muss eine konkrete Karte eindeutig unterscheiden da Kartennamen allein dafür ungeeignet sind.
