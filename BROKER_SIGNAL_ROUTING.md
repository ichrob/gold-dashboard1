# Bob: broker-neutrale Analyse und getrennte Ausführung

## Verbindliches Nutzermodell (13. Oktober 2026)

**DEGIRO bleibt manuell.** Bob erstellt und erklärt Markt-/Produkt-Signale, einschließlich LONG/SHORT/ABWARTEN, aber liest keine DEGIRO-Konto-Orders aus einer nicht vorhandenen offiziellen API und sendet keinerlei DEGIRO-Orders. Der Nutzer kontrolliert den angebotenen Preis und handelt eigenständig. Eine fehlende brokerseitige ausführbare Quote darf den **Marktrichtungswert** nicht automatisch als unbrauchbar markieren; für eine konkrete Produktauswahl sind aktuelle, korrekt datierte Produktdaten weiterhin notwendig. Ein SG-Chartkurs ist kein versprochener Kaufpreis.

**Weitere Broker:** Die Analyse-/Signal-Engine soll später einen offiziellen API-Broker-Adapter mit eigenem Instrumentenmapping erhalten. Der vorhandene reine Vertrag in `broker_bridge.py` listet IBKR (Web API, conid) und IG Bank Schweiz (REST/Streaming, epic). Eine DEGIRO-ISIN wird bei IG nicht automatisch als dasselbe Instrument vorausgesetzt: Gold-CFD, Spot-Gold und SG-Knock-out haben unterschiedliche Kosten, Preisbildung, Barrieren, Vertragsgrößen und Risiken.

## Umsetzung in dieser Änderung

`broker_bridge.route_signal(broker, direction, isin=None)` erstellt nur einen sicheren nichtausführenden Handoff:

- DEGIRO + LONG/SHORT: `DEGIRO_MANUAL_SIGNAL`, keine Broker-Quote als verifiziert markiert.
- IG/IBKR + LONG/SHORT: `API_ADAPTER_NOT_CONNECTED`, vorläufig ohne Kontraktzuordnung.
- NEUTRAL/ABWARTEN: `NO_ACTION` für alle Broker.

Alle Wege haben `paperOrderEnabled=false`, `liveOrderEnabled=false` und `orderSubmitted=false`. Bestehende `BrokerAdapter.submit_order`-Sperre bleibt bestehen. `broker_bridge.status()` macht den manuellen DEGIRO-Modus sowie die vorbereiteten API-Broker öffentlich im bereits vorhandenen, lesegeschützten Research-Status erkennbar. Die Rubrik *Vollautomatisch* zeigt den getrennten Status.

## Freigabestufen für einen später ausgewählten API-Broker

1. **Read-only:** Offizielle API und berechtigtes Konto verbinden, Instrument (conid/epic), Produktart, Handelsplatz, Währung, Kursart, Lizenz und Handelsrechte unabhängig prüfen. Kein Konto wird ohne ausdrückliche Nutzerentscheidung verbunden.
2. **Papier/Demo:** Historische und vorwärtslaufende Signalregeln gegen echte datierte Quellen prüfen; ein eindeutiger Order-ID- und Zustandsautomat verhindert Doppelorders. Stop/TP, Slippage, Gebühren, Handelszeiten, Knock-out und Quote-Veralterung werden broker-spezifisch getestet.
3. **Risikosperren:** Limits für Positionsgröße und Tagesverlust, Maximalpositionen, Not-Aus, Neustart-/Netzfehler, Orderzustands-Abgleich, Broker-Quittung und manuelle Freigabe.
4. **Live (zukünftig, separat):** Nur nach namentlicher Brokerwahl, bestätigter Kontoberechtigung, belegter Produkthandelbarkeit, gesonderter Freigabe der Echtgeld-Ausführung und erfolgreichen kontrollierten Tests. Die bisherige Version eröffnet **nie** echte Orders.

## Quellen

- IBKR offizielle Web API: https://www.interactivebrokers.com/docs/web-api/introduction
- IG Bank Schweiz API/Demo: https://www.ig.com/en-ch/trading-platforms/trading-apis/how-to-use-ig-api
- DEGIRO bietet keine offizielle Konto-API: https://www.degiro.ch/helpdesk/de/handelsplattform/bietet-degiro-eine-api

Die bisherige SG-Datenprüfung und die gesperrte automatische Echtgeld-Handelsfreigabe bleiben unberührt.
