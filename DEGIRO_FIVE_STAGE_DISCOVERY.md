# Bob – fünf sichere Stufen der DEGIRO-Goldproduktrecherche (26.10.2026)

## Getrennte Datenrollen

1. **SnapTrade-Kontosymbolsuche:** Die offizielle SnapTrade-Referenz dokumentiert `POST /accounts/{accountId}/symbols` mit `substring` (maximal 20 Treffer). Bob prüft höchstens **eine fest im bereits früher bestätigten DEGIRO-Listenbestand vorhandene ISIN** je Prozess, nach einem erfolgreichen verschlüsselten Depot-Leseabgleich und nur bei genau einem eindeutig lesbaren Konto. Die eine zusätzliche Anfrage wird nicht wiederholt, unabhängig von HTTP-Fehler oder Rate-Limit. Keine neue DEGIRO-Anmeldung, keine Ordervorschau und keine gespeicherten Konto-IDs im Status.
2. **Historische Emittentenforschung:** Die bisherige 5-Minuten-Rotation über die höchstens 80 aus bereits gelesener Historie klassifizierten Gold-KO-Kandidaten behält bis zu 80 datierte Ergebnisse über mehrere Zyklen im Prozessspeicher. Höchstens zwei zusätzliche vorhandene Emittenten-Lookups pro Zyklus; keine zusätzliche SnapTrade-Transaktion oder vollständige DEGIRO-Katalogbehauptung.
3. **Emittenten-Geld/Brief und Originalzeiten:** Nur exakte ISIN, Gold-Spot, passende Richtung, Nicht-Faktor, aktiver Status, berechtigte originale **vier** Quellzeiten (Geld, Brief, Hebel und Snapshot) im 90-Sekundenfenster und ein gültiges Geld-/Briefpaar werden in der getrennten Vergleichsbeobachtung übernommen. Ein berechneter Hebel ist kein originaler Emittentenhebel. Ältere Werte erhalten im Browser sofort die Kennzeichnung historisch. Keine automatische Broker-Ausführbarkeit.
4. **Screenshots nur bei Nachweislücken:** Derselbe heute gültige, bereits unabhängig geprüfte Produktdetail-Screenshot bleibt pro ISIN bis zur ursprünglichen Frist (22 Uhr Zürich) wiederverwendbar. Durch bloßes erneutes Lesen werden Original-Kurs- und Bildzeiten nicht verlängert. Die private Prüfübersicht zeigt die Zahl wiederverwendbarer aktueller Identitäten.
5. **Streng getrennte Forschungs-Top-3:** Eine hypothetische Forschungsrangfolge wird erst erzeugt, wenn für dieselbe ISIN KO-Abstand, originaler Emittentenhebel und Finanzierungskosten als echte numerische Kennzahlen vollständig vorliegen. Fehlendes wird nicht geschätzt, aus Basispreis/Spread hergeleitet oder ergänzt. Reihenfolge KO-Abstand absteigend, Hebel absteigend, Finanzierungskosten aufsteigend. Keine Änderung an Bobs produktiver Top-3-Auswahl, Risiko-/KO-Regeln oder Produktfreigabe.

## Abnahme und Einschränkungen

- Automatische Produktsuche über DEGIRO und verbindliche DEGIRO-Ausführungskurse bleiben **nicht verfügbar**. DEGIRO bietet keine offizielle Konto-API und unterstützt keine externen Kontoskripte.
- Eine positive Symbolsuche weist höchstens einen Kontosuchkandidaten nach, **keine** aktuelle Handelbarkeit. Leere/fehlgeschlagene Suchen belegen **keine** Unhandelbarkeit.
- Bestehende aktuelle benutzerbestätigte DEGIRO-Listenidentitäten werden durch die neue Forschung weder gelöscht noch überschrieben.
- CI und Tests dürfen niemals mit echten DEGIRO-Quotes, vollständigem Gold-Katalog oder Samsung-Nachweisen verwechselt werden.

Quellen: https://docs.snaptrade.com/reference/Reference%20Data/ReferenceData_symbolSearchUserAccount , https://docs.snaptrade.com/docs/request-signatures , https://docs.snaptrade.com/docs/ratelimiting , https://www.degiro.ch/helpdesk/de/handelsplattform/bietet-degiro-eine-api

Tests: `python -m unittest -v test_degiro_research_review test_snaptrade_account_symbol_probe test_degiro_catalog test_snaptrade_catalog_probe test_snaptrade_cadence test_broker_candidate_evidence`; anschließend vollständige PR-CI, Main-CI, beide Render-Deploys, privater Live-Lesezugriff und (nur falls gewünscht) sichtbarer Android-Test.
