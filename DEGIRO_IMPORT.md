# Manueller DEGIRO-Import: Zeitnachweise

Eine Morgenliste erfasst Produktidentität und Richtung. Bob speichert nur Name,
ISIN und Richtung im Browser. Beim Neustart werden keine Kurse, Hebel, KO oder
Bestätigungen als aktuell wiederhergestellt. Zusatzbilder müssen eindeutig zur
ISIN gehören. Bei LONG/SHORT werden neue Bilder nur für passende Produkte
angefordert; bei NEUTRAL gibt es keine aktuelle Produktauswahl.

Geld, Brief und der daraus berechnete Spread müssen höchstens 90 Sekunden alt
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

Die bestehende automatische BNP-Recherche bleibt erhalten. Die neue SG-Recherche
nutzt die offiziellen Endpunkte `Products/{ISIN}` und `Products/AllProperties/{ID}`.
Sie bestätigt die Produktidentität und zeigt Basiswert, Richtung und KO-Barriere
getrennt von Kursdaten. `AllProperties.TimeStamp` datiert nur den Geldkurs und
enthält keine Zeitzone; Briefkurs und Hebel haben keine eigenen Quellenzeiten.
Deshalb bleiben SG-Produkte für die aktuelle Rangliste gesperrt. Die Abfragezeit
und der Zeitstempel aus `Prices/Live` ersetzen diese fehlenden Angaben nicht.
Es werden keine Konten, API-Schlüssel oder kostenpflichtigen Dienste benötigt.

Tests: `node test_manual_import.js`, `node test_bob.js`, `node validate_bob.js`
und `python -m unittest test_auth.py test_ocr_assets.py test_product_quotes.py`.
Originalbildtests müssen zusätzlich mit den tatsächlichen DEGIRO-Bildern
erfolgen; die Textfixtures testen bewusst die Regeln, nicht die OCR-Genauigkeit.

## Produktbezogener Ablauf

Alle gespeicherten Produkte erhalten direkt einen Upload-Button, auch bei
ABWARTEN. Zur Signalrichtung passende Produkte stehen zuerst. Mehrere Bilder
für dieselbe ISIN werden in der ausgewählten Reihenfolge gelesen. Das gleiche
Bild kann erneut gewählt werden. Abweichende oder fehlende ISIN bleiben gesperrt.
Werte und Quellenzeiten können direkt auf der Produktkarte bestätigt werden.

Zeitlich vollständige, bestätigte Momentaufnahmen werden separat nach technischer
Passung verglichen, nur bei frischem Goldpreis und bestätigter LONG-/SHORT-Richtung.
Schwacher oder widersprüchlicher technischer Konsens sperrt den Vergleich.
Die Rangfolge umfasst nur belegte Momentaufnahmen und bietet keine Live-Freigabe.
Die vorhandene datierte Emittentenrecherche bleibt davon getrennt.

## Automatische Recherche importierter ISINs (02.10.2026)

Bob recherchiert alle gültigen importierten ISINs beim Öffnen sowie erneut nach
60 Sekunden, solange die Ansicht sichtbar ist. Maximal zwei Anfragen laufen
gleichzeitig. Beim Zurückkehren zur Ansicht oder nach Wiederherstellung der
Internetverbindung werden fällige Produkte erneut geprüft. Fehlgeschlagene
Abfragen werden erst im nächsten Zyklus wiederholt. Neue Listen ersetzen
ausstehende Produktidentitäten; alte Antworten werden nicht übernommen.

„Analyse erneut ausführen“ wartet auf den laufenden Recherchezyklus. Die
ISIN-Bestätigung und alle bisherigen Zeit-, Modell- und Ranglistenprüfungen
bleiben erforderlich. Ein neuer Abruf erneuert keine Quellenzeit; ein alter
Kurs bleibt alt. Berechnete Werte bleiben ausdrücklich Schätzungen.

Verwendet werden ausschließlich die bereits vorhandenen externen Adapter,
keine DEGIRO-Kontositzung. Diese Änderung führt keine neue Datenquelle oder
Lizenz ein und belegt keine Anbietererlaubnis. Die Zulässigkeit einer dauerhaften
SG-/Sekundärquellen-Anbindung und vollständige Kursverfügbarkeit für alle ISINs
sind weiterhin gesondert nachzuweisen. Bei geschlossenem Bob startet dieser
Browserzyklus keine Anfragen; die getrennte GCZ26-Sammlung bleibt unverändert.

Onvista untersagt automatisierte Abfragen ohne ausdrückliche Einwilligung:
https://www.onvista.de/nutzungsbedingungen . Deshalb ist der Onvista-Adapter
serverseitig standardmäßig gesperrt, einschließlich seines GCZ26-Fallbacks.
Die primäre Yahoo-GCZ26-Sammlung wird nicht geändert. Die Sperre darf nur mit
dokumentierter Anbietereinwilligung aufgehoben werden (`BOB_ONVISTA_AUTOMATION_APPROVED`
= `provider-approved` und `BOB_ONVISTA_PERMISSION_REFERENCE` als Nachweisreferenz).
Eine Nutzerfreigabe oder öffentlich sichtbare Kurse sind kein solcher Nachweis.
Ohne Erlaubnis bleiben die betroffenen SG-Kurse ausdrücklich offen; manuelle
Screenshotnachweise können weiterhin geprüft werden.

## Pflichtdaten der abschließenden Top 3 (03.10.2026)

Die sichtbare abschließende Auswahl prüft zusätzlich Bezugsverhältnis,
Basispreis in USD, exakten Basiswert, Produkttyp, Produktwährung, Laufzeit und
Quanto-Eigenschaft. Bei Futures ist der exakte Kontrakt erforderlich, zum
Beispiel GCZ26; „Gold“ allein reicht nicht. Faktorprodukte sind ausgeschlossen.
Quanto-Produkte bleiben ohne eigenes bestätigtes Modell gesperrt.

Produktbedingungen besitzen einen eigenen Quellenstand. Die konservative
Gültigkeitsgrenze beträgt 24 Stunden, Kursnachweise bleiben bei 90 Sekunden.
Das ist eine Prüfregel und keine Aussage über Änderungsintervalle des Emittenten.
Fehlende oder zukünftige Zeitangaben sperren die abschließende Auswahl. Ein
historisch gespeicherter fester KO-Wert allein reicht dafür nicht mehr aus.
Die bisherigen Schätzungs- und Teilanalysen bleiben technisch erhalten;
eine neu berechnete Schätzung erneuert keinen alten Geld-/Briefkurs.

Aus Produktdetailbildern werden beschriftete Angaben erkannt, beispielsweise
`Bezugsverhältnis: 0,100`, `Basispreis: 4.460,00 USD`, `Basiswert: XAU/USD`,
`Produkttyp: Turbo`, `Produktwährung: EUR`, `Laufzeit: Open End`, `Quanto: Nein`.
Für ein Future-Produkt kommen `Basiswert: Gold Future Dec 2026` und
`Future-Kontrakt: GCZ26` hinzu. Der tatsächlich belegte Quellenstand wird über
`Produktdatenstand` oder `Bedingungenstand` mit vollständigem Datum, Uhrzeit
und Zeitzone gelesen. Der KO behält seinen eigenen Nachweis `KO-Zeit`.
Labels oder Zeitangaben dürfen nicht erfunden werden. Fehlt der Stand im
Original, zeigt Bob ihn als fehlend an; ein erneuter Upload behebt das nicht.
Fälligkeiten erfordern einen eindeutigen Zeitpunkt; Open End muss explizit
belegt sein. Widersprüchliche Mehrfachwerte werden zurückgewiesen.

Reine Detailbilder erhalten Geld-/Briefwerte, Bildquelle und sämtliche
Kurszeitfelder. Neue Kursbilder ersetzen diese zusammen; ein undatiertes neues
Kursbild darf keine alte Kurszeit erben. Produktbedingungen behalten ihre
eigenen Quellenzeiten. Daten einer anderen ISIN werden nie zusammengeführt.
Ein Produktdatenstand oder Fälligkeitsdatum wird nicht als Kurszeit verwendet.

Regressionstest: `node test_selection_flow.js` umfasst den Weg von OCR-Texten
über beide Bildreihenfolgen, Zusammenführung, Pflichtdaten- und Altersprüfung
bis zur Top 3. Synthetische OCR-Texte belegen keine Erkennungsquote realer Bilder.
