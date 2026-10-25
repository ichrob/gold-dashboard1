# Erweiterte DEGIRO-Leseintegration in Bob (21.10.2026)

Die folgenden Funktionen verwenden **nur ausdrücklich autorisierte, lesende**
SnapTrade-Personal-Zugriffe und vom Nutzer importierte CSV-Daten.

## Bereits vorhandene Bausteine
- SnapTrade-Personal-Einrichtung unter Mehr → DEGIRO. Schlüssel verschlüsselt.
- Konten, Bestände, Bargeld und Bewertungskurse, mit Quellzeitstempeln.
- Order-Journal und tägliche Kontotransaktionen, verschlüsselter Verlauf.
- Expliziter/automatischer CSV↔ISIN-Abgleich mit Konfliktprüfung und Originalidentität.
- Separate aktuelle Produkt-/Emittentenkurse bei eindeutiger ISIN, jedoch **keine
  ausführbaren DEGIRO-Kurse oder Handelsplatznachweise**.
- Benutzerexport im Browser; kein heimliches Einloggen oder automatischer Upload.

## Diese Erweiterung
- `snaptrade_trade_insights.py`: Prüfliste echter, vom Anbieter mit positiver
  `filled_quantity` gemeldeter Orderausführungen. Nur eindeutige bestehende
  CSV-/ISIN-Zuordnungen und gleiche Symbol-/Währungskennung zählen als zugeordnet.
  Zeit nur bei Original-Zeitstempel mit Zeitzone. Duplikate werden ignoriert.
- Ausgewiesene Gebühren werden aus täglichen Transaktionszeilen **nach Währung**
  addiert; ohne Wechselkursannahmen, zusätzliche Kostenannahmen oder erfundene
  Vorzeichenkorrektur. Kein berechneter Netto-Trading-Gewinn.
- Neue, einklappbare DEGIRO-Prüfansicht, sauber getrennt von Mein Trade und
  dem Gold-Produkt-Ranking. Status der Ursprungskonten bleibt sichtbar.
- Lokales CSV-Einfügen auf dem Android-Handy als Alternative zur Dateiauswahl.
- Tests für doppelte Orders, unbestätigte Identität, fehlende Zeitstempel,
  Gebührensummen und unveränderte Handelsblockaden.

## Wichtig: Was noch nicht automatisch möglich ist

1. **Echtzeit-Trades:** SnapTrade liefert je nach Broker-/Tarif-Kombination
   Intraday-Orders oder nur zwischengespeicherte Daten. 10-minütliche
   Holdings-Abrufe bei geöffneter DEGIRO-Ansicht und sechs Stunden im
   Hintergrund sind kein 30-s-Echtzeit-Trading-Feed.
2. **Vollständige echte Trade-Ergebnisse:** Ein Kauf und ein Verkauf müssen
   erst sicher durch Ausführungsnachweise, Stückzahl, Währung, Gebühren,
   Produktnotierung, Zeit und Kontokontext zugeordnet sein. Die neue Liste
   ist ein Kandidatenbestand für einen späteren historischen Vergleich mit
   Bobs damaliger Marktentscheidung. Sie lernt noch nicht aus diesen
   Kandidaten, weil eine fehlende historische Empfehlung nicht erfunden wird.
3. **Android-Berechtigungen:** Das direkte Einfügen benötigt keine
   Android-Zusatz-App. DEGIRO-Mitteilungen, App-Screens oder Kontozugänge
   werden nicht im Hintergrund ausgelesen.
4. **PDF/XLSX:** Für diese Formate ist aktuell **keine** neue Importlogik
   freigegeben. Bitte weiterhin CSV verwenden. Ein PDF-/Excel-Konverter
   darf keine frei erfundenen Originalzeiten oder Finanzwerte erzeugen.
5. **ChatGPT-Connector:** SnapTrade bietet einen eigenen **schreibgeschützten**
   MCP-Server: https://docs.snaptrade.com/docs/mcp-server . Die Installation
   erfordert eine separate Aktion des Kontoinhabers; Bob kann weder diese
   ChatGPT-Verbindung noch die Anbieterberechtigungen heimlich aktivieren.
6. **DEGIRO:** Laut offizieller DEGIRO-Dokumentation gibt es keine eigene API,
   externe Konto-Skripte/Trading-Bots werden nicht unterstützt.
   Keine Echtgeldorders, Handelsplatz-Freigaben oder Risiko-/KO-Regeländerungen.

## Verifizierung

```bash
python -m unittest test_snaptrade_trade_insights test_snaptrade_bridge test_snaptrade_portfolio
node test_degiro_export_mobile.js
python -m py_compile snaptrade_trade_insights.py snaptrade_bridge.py snaptrade_panel.py
```

GitHub-CI und Render-Deployment werden nach Zusammenführung gesondert geprüft.
Ein erfolgreicher Test mit künstlichen Daten ist **kein** Nachweis für eine
aktuelle DEGIRO-Abdeckung eines Knock-out-Produkts.

## Anbieterbegrenzung und historische Abrufe (25.10.2026)

SnapTrade Personal setzt standardmäßig **10 gemeinsame Konto-API-Anfragen je
Minute** durch (Positionsdaten, Guthaben, Orders und Aktivitäten teilen sich
jeweils das Budget desselben Kontos). Die bisherige Batch-Liste enthielt bis
zu 13 Aktivitätenseiten und konnte zusätzlich zu 3 weiteren Kontoanfragen
HTTP 429 auslösen. Referenz: https://docs.snaptrade.com/docs/ratelimiting

Der tägliche historische Leseversuch umfasst nun **höchstens fünf Seiten à
500 Buchungen**; mit drei üblichen zusätzlichen Kontoendpunkten sind das
höchstens acht kontoabhängige Requests in diesem Zyklus. Andere Clients können
das gemeinsame Limit trotzdem ausnutzen. Ein 429 wird nicht mit sofortigen
Neuanfragen beantwortet: Es verbleibt beim bestehenden täglichen
Aktivitätenintervall. Früher bestätigte Datensätze und deren Quellzeitpunkte
bleiben erhalten. Der letzte Versuch erhält einen statischen Fehlercode und
die Zahl zuvor erfolgreich gelesener Seiten; nicht vollständig geholte Seiten
werden nicht als neu bestätigte Daten übernommen.

Der Fix hebt einmalig die Journalschema-Version an und erlaubt dadurch **einen**
neuen, auf fünf Seiten begrenzten Prüfversuch beim nächsten regulären
SnapTrade-Depotlinesezyklus. Dies ist kein 24-Stunden- oder Live-Order-Feed.
Die Anbieterhistorie ist mit über 12.000 Buchungen länger als das sichere
Tagesfenster. Eine vollständige FIFO-Gewinnrechnung bleibt deshalb gesperrt,
bis eindeutige, vollständige Nachweise ohne Rate-Limit-Verstoß vorliegen.

## Getrennte historische BUY-/SELL-Abdeckung (25.10.2026)

SnapTrade erlaubt den expliziten Aktivitätenfilter `type=BUY,SELL`. Der direkte,
autorisierte Lesetest hat **2.704** derart gekennzeichnete Buchungen gemeldet,
während die unselektierte DEGIRO-Historie **12.599** Einträge meldete.
Dies ist ein Anbieter-Beobachtungsstand, keine dauerhafte feste Stückzahl.

Bob führt deshalb einen zusätzlichen **höchstens wöchentlichen** historischen
GET-Lesetest durch, jedoch ausschließlich in einem regulären Depotzyklus,
in dem die täglichen **ungefilterten** Aktivitäten noch nicht erneut fällig
sind. Beide Historien dürfen niemals in demselben Abrufzyklus gestartet
werden. Es werden nur maximal **3 × 1.000** gefilterte Zeilen per Konto
abgerufen, neben höchstens einer Order- und je einer Positions-/Guthaben-
abfrage. Nur die exakten Parameter `type=BUY,SELL`,
`limit=1000`, `offset=0/1000/2000` sind zusätzlich freigegeben.
Kein neues Verfahren zum Broker-Login, kein Realtime-Refresh, kein
kostenpflichtiger Abruf, keine Orders.

Es wird **keine Liste einzelner Trades** zusätzlich archiviert: Nur gezählte
Käufe/Verkäufe, den gemeldeten Gesamtumfang, ISIN-Prüfzahlen, sichere
Übereinstimmungen mit *bereits* nachgewiesenen aktuellen Depot-ISINs,
Anbieter-Tagesdatenbereich und Vollständigkeit des gefilterten Ausschnitts
werden verschlüsselt im bestehenden persönlichen Journal gespeichert.
Rohe Konten-/Order-/Transaktions-IDs, persönliche Texte und Details werden
nicht in die Diagnostik oder GitHub übernommen. Provider-429, ein nicht
eingehaltenes Filterkriterium, Doppelkollisionen oder fehlende Seiten lassen
den Datensatz ausdrücklich **unvollständig** oder **unverfügbar**. Ein früherer
bestätigter Stand bleibt mit seiner Originalprüfzeit erhalten; keine sofortige
Wiederholung nach Fehler.

Die gefilterte BUY-/SELL-Historie ist **niemals eine vollständige
Bestandshistorie**. Überträge, Kapitalmaßnahmen, Sonderfälle, Gebühren, Steuern,
Cash-Sweeps und etwaige unbekannte Typen fehlen dabei. Der Filter darf
`historyComplete`, `fifoEligible`, Trade-Freigaben, Bobs reale/virtuelle
Gewinnzahlen und das Strategielernen nicht verändern. Originale ISINs sind
nur über die bestehende Checksumme und bestätigte CSV-Identitäten vergleichbar.
Ohne alle Belege bleiben historische P/L-Resultate ausdrücklich offen.

## ISIN-basierte Einzelübersicht ohne neue Anbieterabfrage (25.10.2026)

Aus dem bestehenden wöchentlichen BUY-/SELL-Filter ergänzt Bob zukünftig
**höchstens 25** nach Prüfziffer bestätigte, heute per CSV zugeordnete
Depot-ISINs um die Anzahl historischer Kauf-/Verkaufsbuchungen und die
frühesten/spätesten Anbieter-*Buchungstage*. Eine ISIN-Zuordnung ist kein
Beweis dafür, dass ein historischer Trade zur heutigen Depotposition
gehört: Überträge, Reinvestitionen, mehrere Konten, Gebühren und
zwischenzeitliche Nullbestände sind dadurch nicht rekonstruiert.

Für die Gesamtübersicht meldet Bob außerdem die Anzahl historischer
BUY/SELL-Buchungen **ohne gültigen ISIN-Nachweis**. Er rät solche
Kennungen niemals anhand von Produktnamen, WKN-Ähnlichkeiten oder
Handelsvolumen. Die per-ISIN-Zahlen enthalten keinerlei einzelne
Anbieter-Transaktions-IDs, Stückzahlen, Preise oder Kontonummern.
Bobs private Diagnostik bleibt auf aggregierte Zähler begrenzt; die
ISIN-Einzeldaten erscheinen nur in der authentifizierten DEGIRO-Ansicht
und im bereits vorhandenen verschlüsselten Portfoliojournal.

**Keine neue Händlerabfrage:** Die bestehende Wochenfrequenz und die
bereits getesteten 3 gefilterten Anbieter-Seiten bleiben unverändert.
Alte bestätigte Filterstände bleiben gültig und zeigen bis zum nächsten
ohnehin fälligen Wochenabruf nur die bisherigen Summen. Es gibt
keinen erzwungenen einmaligen Refresh wegen dieses UI-Ausbaus.
Selbst eine vollständig eingelesene BUY-/SELL-Auswahl schaltet
weder historische FIFO-Gewinne noch Stopps, Echtgeldorders oder
automatisches Strategielernen frei.
