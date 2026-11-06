# Anwendung im Data Warehouse

## **Supervised Learning:** 

Vorhersagen und Klassifizierung (basierend auf bekannten Zielwerten) 

## **Unsupervised Learning:** 

Gruppen/Muster/Zusammenhänge erkennen (die man vorher nicht kennt) 

## **Regression:** 

Vorhersage anhand historischer Daten (z.B Umsatz, Nachfrage, Verkaufszahlen) 

## **Decision Tree, Random Forest:** 

DT: ein Entscheidungsbaum → Entscheidung anhand von festen Regeln RF: Kombinationen mehrerer Entscheidungsbäume → robuster als Decision Tree 

## **SVM:** 

Klassifizierung anhand von Grenzen (z.B, Funktion), vor allem auch hochdimensional 

Mobilfunkunternehmen können mit einem „Support Vector Machine“-Modell Kunden identifizieren, die nach Ablauf der Mindestvertragslaufzeit ihren Vertrag kündigen, und können dann mit Rabattaktionen den Kunden möglichst versuchen am Unternehmen zu binden. Ebenso können Kunden erkannt werden, bei denen es sinnvoller ist, sie nicht auf das Ende der Vertragslaufzeit hinzuweisen, (weil es eben genau dann dazu kommen kann, dass sie kündigen,) um sie als Dauerkunden zu behalten. 

Bedingungen: 

- sinnvolle Messwerte 

- historische Daten 

## **Naive Bayes:** 

nutzt (bedingte) Wahrscheinlichkeiten für Klassifizierung (Satz von Bayes), z.B Textklassifizierung in positiv/negativ 

## **K-Means-Algorithmus:** 

Versuch, Klassen zu identifizieren, die vorher nicht festgelegt sind; z.B. Klassifizierung von Kunden nach hoher Einkaufswert, billige Produkte, Produktgruppen 

## **PCA (Principle Component Analysis):** 

Reduktion der Anzahl von Merkmalen, bleibt dabei möglichst genau; erfasst vor allem lineare Zusammenhänge; Beispiel: 1000 Kundenmerkmale, davon aber vielleicht nur wenige relevant bzw. viele voneinander abhängig → Ermittlung der wichtigen Merkmale 

## **T-SNE (T-distributed Stochastic Neighbor Embedding):** 

Reduktion auf zwei- bzw dreidimensionale Visualisierung, dabei möglichst Erhalt von Nachbarschaften (hauptsächlich Visualisierung, eher weniger für tatsächliche Klassifizierung) 

## **Apriori algorithm:** 

Erkennung von häufig gemeinsamen Merkmalen (Kunden die A kauften, kauften häufig auch B) Beispiel Amazon: 

Vorschlagen von häufig zusammen gekauften Artikeln 

Bedingungen: 

Datenbank über Kundenkäufe 

selten wechselnde Produkte (ergibt nur Sinn, wenn Produkte über einen längeren Zeitraum verfügbar sind, andernfalls würden Empfehlungen auf nur wenigen Datensätzen basieren) 

## **Welche Möglichkeiten bietet ein Data Warehouse, die Arbeitsschritte Data Collection, Data Cleaning, Feature Engineering und Exploratory Data Analysis zu unterstützen?** 

_Data Collection:_ 

In der Staging Area werden Daten aus unterschiedlichen Quellsystemen extrahiert und zusammengeführt. 

_Data Cleaning:_ 

Nach dem Staging werden Daten transformiert, themenspezifisch gegliedert, normalisiert (z.B. Stuttgarter Str. einheitlich in Stuttgarter Straße) sowie Bewegungsdaten mit Stammdaten verknüpft. Die Daten werden dabei in ihre Bestandteile zerlegt (z.B. Adressen in Straße, Hausnummer, etc.) und auf Plausibilität geprüft (z.B. ob Postleitzahl zur angegebenen Stadt passt). So können auch fehlerhafte, unvollständige oder doppelt auftretende Datensätze erkannt und behandelt werden. 

_Feature Engineering:_ 

Ziel des Feature Engineering ist aus vorhandenen Daten neue Merkmale für die Analyse zu erzeugen. Im Data Warehouse geschieht dies vor allem durch die Berechnung neuer Kennzahlen und die Kombination von Daten aus verschiedenen Relationen. 

### _Exploratory Data Analysis (EDA):_ 

EDA dient der Untersuchung von Daten, der Erkennung von Mustern und dem Verstehen von Zusammenhängen. Im Data Warehouse kann dies durch Datenzusammenführung ermöglicht werden, wobei Daten über einen bestimmten Zeitraum, eine Region oder verschiedene Kundengruppen betrachtet werden. 

