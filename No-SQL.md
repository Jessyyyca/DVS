# NoSQL 

## **Möglicher Anwendungsfall:** 

Onlineshop mit sehr unterschiedlichen und oft wechselnde Produktkategorien & Struktur der Daten (Kleidung, Bücher, Hundefutter) → für die Produkte müssen unterschiedliche Informationen gespeichert werden Aufwendig in relationalen Datenbanken, da für jedes Produkt eigene Tabellen; in NoSQL einfacher (z.B. durch Speicherung in JSON) 

anderer Anwendungsfall: 

Online-Messaging Plattform mit sehr hohem Nachrichten-Druchsatz 

- Ob Nachricht A schon konsistent in der Datenbank vorliegt, ist für Nachricht B oft egal 

- - höhere Datendurchsätze (z.B. Nachrichten pro Sekunde) durch NoSQL (z.B Cassandra), indem auf Konsistenz verzichtet wird und "eventual consistency" ausreichend ist 

- Bessere Skalierbarkeit des Nachrichtendienstes, da bei NoSQL eben dieser KonsistenzOverhead, im Sinne von Schreibblockaden, entfällt 

## **Vorteile und Nachteile gegenüber relationalen Datenbanken:** 

## Vorteile 

- <u>bessere horizontale Skalierbarkeit durch Distributisierung der Daten über ein Cluster von</u> Datenbankknoten (sowohl Performance als auch Verfügbarkeit) 

- Schemata nicht notwendig 

- für größere Datenmengen (Datendurchsatz) besser geeignet 

- flexible Struktur 

## Nachteile 

- oft weniger robust 

- weniger starke Konsistenzgarantien (CAP-Theorem) → Eventual Consistency 

- BASE (basically available, soft state, eventual consistency) statt ACID (atomicity, consistency, isolation, durability) 

