# DEGIRO-Bildschirmkurs vs. Emittentenangebot – datierter Abgleich

Stand: 26.10.2026. **Kein automatischer ausführbarer DEGIRO-Kurskanal.**

## Technisch zulässig und implementiert

- Bobs bereits vorhandener, authentifizierter Screenshotbeleg enthält die exakt validierte ISIN, EUR/CHF, benannten Handelsplatz, Bild-Fingerabdruck und angezeigte Uhrzeit. Ein heutiger Listungsnachweis bleibt nur bis zu seiner bisherigen Grenze (22:00 Europe/Zurich) gültig.
- Ein davon unabhängiger **Bildschirmpreisstatus** gilt höchstens 90 Sekunden ab der **angezeigten Bildschirmminute**. Er ist ausdrücklich **kein** Originalzeitstempel beider Börsen-Geld/Brief-Seiten und keine DEGIRO-Orderquote. Das erneute Lesen des Datensatzes verjüngt die Quelle nicht.
- Der Emittentenvergleich akzeptiert nur genau dieselbe ISIN/Währung, eindeutig passenden BNP-OTC- beziehungsweise Société-Générale-OTC-Handelsplatz, nachgewiesene Quellherkunft und alle vier separat datierten Emittentenfelder (Bid, Ask, Hebel, Snapshot). Bildschirm- und Emittentenzeitfenster müssen höchstens 90 Sekunden auseinanderliegen.
- Berechnet die maximale relative Preisabweichung zwischen Bildschirm-Geld und Emittenten-Geld sowie Bildschirm-Brief und Emittenten-Brief. Bei über 1 % wird **Abweichung**, andernfalls **ähnliche Anzeige** gemeldet. Kein Spread-Abzug im Produktranking und **keine** Handelsfreigabe aus Übereinstimmung.
- Bei veraltetem Bildschirm, fehlendem Anbieter-Quellzeitpunkt, falschem Handelsplatz/ISIN, abweichender Währung, künstlich datiertem Quote, fehlendem Geld/Brief oder nicht nachweisbarer Quelle erscheint nur **nicht vergleichbar**.
- Produkt- und Kundeninformationen bleiben im bestehenden privaten Bericht. Die neue Anzeige führt keine zusätzlichen Requests an den Broker oder Emittenten aus und sendet keine Orders oder E-Mails.

## Nachweisgrenzen

1. Die offiziell dokumentierte DEGIRO-Plattform hat keine Konto-API; automatisierte Drittanbieter-Konto-Skripte werden nicht unterstützt. Daher kein inoffizieller Login, Browser-Roboter, Order-Simulation oder verdecktes Abgreifen der persönlichen Brokerkurse.
2. SnapTrade liefert Konten und Depotpositionen, aber die produktive DEGIRO-Instrumentenliste und die anschließende accountbezogene Symbolsuche lieferten aktuell 0 Treffer. Das ist **kein Beweis** für Unhandelbarkeit eines bestimmten Gold-Knock-outs.
3. SnapTrade **Account Quotes** sind laut Hersteller kein Echtzeit-Marktdatenfeed; können verzögert sein. Sie werden nicht zu einem ausführbaren Geld-/Briefpaar umetikettiert. Der bestehende DEGIRO-/SnapTrade-Leseabgleich und die konservativen Rate Limits bleiben unverändert.
4. Ein vollständig aktueller, verbindlich ausführbarer Orderpreis kann erst nach Bereitstellung eines offiziell autorisierten Brokerkanals mit eindeutigem Konto-/Instrumentbezug, originaler Quote-ID, separaten Originalzeiten, Gültigkeit, Volumen und Handelskonditionen verifiziert werden. Aktuell **nicht** verfügbar.
5. Anzeige- und Entwickler-Tests belegen nur die getrennte Klassifizierung; weder eine aktuell ausführbare DEGIRO-Order noch den Empfang auf dem Samsung-Gerät.

Quellen: https://www.degiro.ch/helpdesk/de/handelsplattform/bietet-degiro-eine-api ,
https://www.degiro.ch/helpdesk/de/handelsplattform/verwendung-der-handelsplattform/kann-ich-mit-degiro-automatisierte-trades-oder ,
https://docs.snaptrade.com/reference/Trading/Trading_getUserAccountQuotes .

Regressionen: `python -m unittest -v test_broker_candidate_evidence test_degiro_research_review` und `node test_broker_candidate_pools.js`; vollständige Python-/JS-/Browser-/Security-CI, Main-CI, Live-Smoke, Render beider Services, privater Diagnosenachweis.
