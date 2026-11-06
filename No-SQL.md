# NoSQL 

## **Möglicher Anwendungsfall:** 

Onlineshop mit sehr unterschiedlichen und oft wechselnde Produktkategorien & Struktur der Daten (Kleidung, Bücher, Hundefutter) → für die Produkte müssen unterschiedliche Informationen gespeichert werden Aufwendig in relationalen Datenbanken, da für jedes Produkt eigene Tabellen; in NoSQL einfacher (z.B. durch Speicherung in JSON) 

anderer Anwendungsfall: 

Online-Messaging Plattform mit sehr hohem Nachrichten-Druchsatz 

- Ob Nachricht A schon konsistent in der Datenbank vorliegt, ist für Nachricht B oft egal 

- - höhere Datendurchsätze (z.B. Nachrichten pro Sekunde) durch NoSQL (z.B Cassandra), indem auf Konsistenz verzichtet wird und "eventual consistency" ausreichend ist 

- Bessere Skalierbarkeit des Nachrichtendienstes, da bei NoSQL eben dieser KonsistenzOverhead, im Sinne von Schreibblockaden, entfällt 

## **Vorteile und Nachteile gegenüber relationalen Datenbanken:** 

### Vorteile 

- bessere horizontale Skalierbarkeit durch Distributisierung der Daten über ein Cluster von Datenbankknoten (sowohl Performance als auch Verfügbarkeit) 

- Schemata nicht notwendig 

- für größere Datenmengen (Datendurchsatz) besser geeignet 

- flexible Struktur 

### Nachteile 

- oft weniger robust 

- weniger starke Konsistenzgarantien (CAP-Theorem) → Eventual Consistency 

- BASE (basically available, soft state, eventual consistency) statt ACID (atomicity, consistency, isolation, durability) 

## **Unsere Implementierung:**

Als No-SQL Datenbank haben wir uns für MongoDB entschieden, da es bereits einige Beispiel-Datensätze zum Importieren anbietet. [Sample Supply Store Dataset](https://www.mongodb.com/docs/manual/sample-data/sample-supplies/) ist der Datensatz, welcher in userem Show-Case genutzt wird und auf welchen sich alle folgenden Beispiele beziehen. 

### Import

Der Datensatz wurde auf dem Server importiert, indem eine Verbindung zum Container hergestellt wurde, auf diesem `curl` installiert wurde und anschließend mithilfe von `curl` der Beispiel-Datensatz heruntergeladen wurde. Mithilfe von `mongorestore` wurde schlussendlich der runtergeladene Datensatz importiert:
```bash
root@vueko ~/d/d/mongodb_service# docker compose exec mongodb bash
root@04ffcd134881:/# apt update && apt install curl
root@04ffcd134881:/# curl -L https://atlas-education.s3.amazonaws.com/sampledata.archive -o sampledata.archive 
root@04ffcd134881:/# mongorestore --archive=sampledata.archive --nsInclude="sample_supplies.*" 
```

### CRUD-Operationen an MongoDB
zu sehen in [mongodb/src/main.py](mongodb/src/main.py)

Alle CRUD-Operationen waren relativ straight forward, da `pymongo` (MongoDBs Python Bibliothek) sehr benutzerfreundlich und an Python angenähert war. Beispielsweise sah wie folgt das Erstellen eines Datensatzes aus:
```py
client = MongoClient(get_dsn())
db = client["sample_supplies"]
sales = db["sales"]

### CREATE
new_sale = {
    "_id": "tutorial_demo_sale",
    "storeLocation": "Berlin",
    "purchaseMethod": "Online",
    "items": [
        {
            "name": "notebook",
            "quantity": 2,
            "price": 12.99
        }
    ],
    "customer": {
        "age": 25,
        "satisfaction": 5
    },
    "couponUsed": False
}

sales.insert_one(new_sale)
``` 

### Migration von MongoDB zu DuckDB

Als relationale Datenbank, in welche wir die MongoDB-Daten beispielhaft migrieren wollen, haben wir uns für DuckDB entschieden. Hierfür gibt es primär zwei Gründe:
- DuckDB ist eine "Analytical Database" und würde somit gut geeignet sein als Data-Warehouse-Datenbank
- DuckDB ist eine In-Memory-Datenbank und daher sehr gut geeignet zum Migrieren von Beispiel-Daten.
Die kommentierte Migrations-Datei liegt unter [mongodb/src/etl_python_duckdb.py](mongodb/src/etl_python_duckdb.py). 
