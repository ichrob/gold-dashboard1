# Manueller DEGIRO-Import: Zeitnachweise

Eine Morgenliste erfasst Produktidentität und Richtung. Bob speichert nur Name,
ISIN und Richtung im Browser. Beim Neustart werden keine Kurse, Hebel, KO oder
Bestätigungen als aktuell wiederhergestellt. Zusatzbilder müssen eindeutig zur
ISIN gehören. Bei LONG/SHORT werden neue Bilder nur für passende Produkte
angefordert; bei NEUTRAL gibt es keine aktuelle Produktauswahl.

Geld, Brief und der daraus berechnete Spread müssen höchstens 60 Sekunden alt
sein. Hebel und KO brauchen jeweils einen eigenen Zeitnachweis, ebenfalls
höchstens 60 Sekunden alt. Dies ist eine konservative Prüfregel, keine Aussage,
dass sich die KO-Schwelle sekündlich ändert. Neue Kursbilder aktualisieren nur
die Kursnachweise. Neue undatierte Hebel-/KO-Werte ersetzen alte Werte und
verlieren deren früheren Zeitnachweis. Reine Produktdetails erhalten die
bisherigen Kursnachweise.

Erkannt werden ausdrücklich zugeordnete Quellenzeiten mit Datum, Sekunden und
Zeitzone, beispielsweise die tatsächlich im Quellbild angezeigte Angabe:

```
Kurszeit: 01/10/2026 06:00:00 CEST
Hebelzeit: 01/10/2026 06:00:00 CEST
KO-Zeit: 01/10/2026 06:00:00 CEST
```

Geldzeit und Briefzeit können getrennt angegeben sein; der Spread verwendet die
ältere Zeit. UTC, Z, CET, CEST und numerische UTC-Offsets werden unterstützt.
Eine alleinstehende Bildschirmzeit, Uploadzeit, Dateidatum, Ablaufdatum oder
eine Zeit ohne Zeitzone wird nicht als Kurszeit verwendet. Fehlende Sekunden,
widersprüchliche Angaben, ungültige Daten, Zukunftszeiten und als verzögert
gekennzeichnete Kurse sperren die zeitlich vollständige Bewertung. Bob ergänzt
keine fehlenden Quellenzeiten. Ein manuell hinzugefügtes Label belegt keine
ursprüngliche Quellenzeit. Der Vergleich nutzt die Browseruhr.

Erkannte Werte und zugeordnete Quellenzeiten müssen am Original geprüft werden.
Der Upload selbst ist keine Bestätigung. Das Alter wird in der sichtbaren App
sekündlich neu geprüft, auch nach einem Richtungswechsel.

Eine zeitlich vollständige Momentaufnahme erhält eine getrennte technische
Prüfung. Sie bestätigt keine laufende Live-Datenversorgung, keinen Marktstatus
und keinen ausführbaren DEGIRO-Kurs. Sie erhält deshalb keine Live-Freigabe und
wird nicht als datierter Emittenten-API-Kurs in die Live-Rangliste eingeschleust.
Die separate manuelle Rechenprüfung besitzt keine Quellenzeiten und bekommt
ebenfalls keine grüne aktuelle Freigabe.

Die bestehende automatische BNP-Recherche bleibt erhalten. Für SG wird keine
verlässliche kostenlose Live-Quelle behauptet. Unterstützte Recherche ist
kein Nachweis, dass ein Produkt aktuell oder handelsgeeignet ist.

Tests: `node test_manual_import.js`, `node test_bob.js`, `node validate_bob.js`
und `python -m unittest test_auth.py test_ocr_assets.py test_product_quotes.py`.
Originalbildtests müssen zusätzlich mit den tatsächlichen DEGIRO-Bildern
erfolgen; die Textfixtures testen bewusst die Regeln, nicht die OCR-Genauigkeit.
