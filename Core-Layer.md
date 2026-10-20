# Core-Layer

## Entity-Relationship-Diagramm der Core-Schicht

Das folgende Diagramm zeigt die Beziehungen zwischen den drei Topic-Tabellen, den gemeinsam genutzten Core-Tabellen und den Dimensionstabellen.

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryTextColor": "#171717", "textColor": "#171717", "lineColor": "#444444", "primaryBorderColor": "#555555", "background": "#ffffff"}}}%%
erDiagram
    DIM_POKEMON {
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
    DIM_DATE {
        int date_id PK
        date full_date
        int day
        int month
        int quarter
        int year
    }
    DIM_CARD {
        int card_id PK
        string card_name
        string set_name
        string rarity
    }
    CORE_DECK_RESULT {
        string deck_id PK
        int date_id FK
        int wins
        int losses
        int ties
    }
    CORE_CARD_PRICE {
        int card_id PK,FK
        string printing_type PK
        int date_id PK,FK
        decimal market_price
    }
    TOPIC_BASE_STATS_VS_COMPETITIVE {
        string deck_id PK,FK
        int pokemon_id PK,FK
        int pokemon_copy_count
    }
    TOPIC_POKEMON_PRICE {
        int pokemon_id PK,FK
        int card_id PK,FK
    }
    TOPIC_CARD_COMPETITIVE {
        string deck_id PK,FK
        int card_id PK,FK
        int card_copy_count
    }

    DIM_DATE ||--o{ CORE_DECK_RESULT : played_on
    DIM_DATE ||--o{ CORE_CARD_PRICE : observed_on
    DIM_POKEMON ||--o{ TOPIC_BASE_STATS_VS_COMPETITIVE : used_pokemon
    DIM_POKEMON ||--o{ TOPIC_POKEMON_PRICE : pokemon
    DIM_CARD ||--o{ TOPIC_POKEMON_PRICE : pokemon_card
    DIM_CARD ||--o{ TOPIC_CARD_COMPETITIVE : used_card
    DIM_CARD ||--o{ CORE_CARD_PRICE : priced
    CORE_DECK_RESULT ||--o{ TOPIC_BASE_STATS_VS_COMPETITIVE : contains
    CORE_DECK_RESULT ||--o{ TOPIC_CARD_COMPETITIVE : contains

    style DIM_POKEMON fill:#EAFBF5,stroke:#009F8C,color:#171717,stroke-width:2px
    style DIM_DATE fill:#FAEBFF,stroke:#BE42DE,color:#171717,stroke-width:2px
    style DIM_CARD fill:#FFF2E6,stroke:#E67714,color:#171717,stroke-width:2px
    style CORE_DECK_RESULT fill:#E5F9FC,stroke:#009DBB,color:#171717,stroke-width:2px
    style CORE_CARD_PRICE fill:#E9FAEF,stroke:#13AB4E,color:#171717,stroke-width:2px
    style TOPIC_BASE_STATS_VS_COMPETITIVE fill:#F1EAFF,stroke:#8655D8,color:#171717,stroke-width:2px
    style TOPIC_POKEMON_PRICE fill:#FFF9DF,stroke:#C79100,color:#171717,stroke-width:2px
    style TOPIC_CARD_COMPETITIVE fill:#FFEBEF,stroke:#DA4C61,color:#171717,stroke-width:2px
```

## Topic-Tabellen

Für jedes der 3 Analyseszenarios wird jeweils eine Topic-Tabelle angelegt. Da zwischen den Topics 
Überschneidungen existieren, haben wir sowohl aus Perfomance-Gründen, als auch um Duplizierungen
von Daten zu vermeiden, entschieden `CORE`-Tabellen zu benutzen.

Dadurch ergeben sich folgende `TOPIC`-Tabellen:

```text
TOPIC_BASE_STATS_VS_COMPETITIVE
--------------------------------
deck_id                 PK, FK
pokemon_id              PK, FK
pokemon_copy_count
```

```text
TOPIC_POKEMON_PRICE
--------------------------------
pokemon_id              PK, FK
card_id                 PK, FK
```

```text
TOPIC_CARD_COMPETITIVE
--------------------------------
deck_id                 PK, FK
card_id                 PK, FK
card_copy_count
```

Beim erzeugen dieser Tabellen musste ein Matching von Namen von Pokemon-Karten mit den Namen von 
Pokemon im Spiel hergestellt werden. Dabei waren vor allem Namenszusätze wie "Ex", "Lv.99", "V" nach 
oder Trainernamen oder ähnliches vor einem Pokemonnamen zu beachten.

## Core-Tabellen

Es ergeben sich zwei `CORE`-Tabellen, die jeweils Daten zu zwei Topics enthalten.

Zu `TOPIC_BASE_STATS_VS_COMPETITIVE` und `TOPIC_CARD_COMPETITIVE`:

```text
CORE_DECK_RESULT
--------------------------------
deck_id                 PK
date_id                 FK
wins
losses
ties
```

Zu `TOPIC_POKEMON_PRICE` und `TOPIC_CARD_COMPETITIVE`:

```text
CORE_CARD_PRICE
--------------------------------
card_id                 PK
printing_type           PK
date_id                 PK, FK
market_price
```

## Dimensions-Tabellen

```text
DIM_POKEMON
--------------------------------
pokemon_id              PK
pokemon_name
hp
attack
defense
special_attack
special_defense
speed
type_one
type_two
```

Beim Befüllen dieser Tabelle war es notwendig, einen Join aus den Tabellen `P_type` 
und `P_pokemon_type` aus dem Staging zu machen, und eine Reihenfolge der entdeckten 
Typen festzulegen.

```text
DIM_DATE
--------------------------------
date_id              PK
full_date
month_day
week_day
month
year
```

```text
DIM_CARD
--------------------------------
card_id              PK
card_name
rarity
```
