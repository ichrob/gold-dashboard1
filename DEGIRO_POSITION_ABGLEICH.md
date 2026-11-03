# Bob – Positionsabstimmung aus DEGIRO-CSV und Ausführungsbestätigungen

## Nutzerziel (3. November 2026)

Bob soll tatsächlich bestätigte DEGIRO-Käufe und -Verkäufe erkennen und mit Depotbeständen abgleichen, ohne manuelle Doppelerfassung und ohne Brokerorders. Die Ausführung eines Kaufs/Verkaufs bleibt ausschließlich bei DEGIRO.

## Vorhandene Quellen

1. **Portfolio-CSV:** Unter `Mehr → DEGIRO` per ausdrücklichem Dateiupload importiert. Lokal im Browser gespeicherter, kompletter Bestand `bob.degiro.csv.depot.v1`; Einlesezeit ist **nicht** die CSV-Export-/Bestandszeit. Keine automatische DEGIRO-Kontoabfrage.
2. **Transaktions-CSV:** Neuer separater lokaler Speicher `bob.degiro.transactions.csv.v1`; pro Zeile ausschließlich ISIN, BUY/SELL, Stückzahl, Produktwährung, Ausführungspreis, Handelstag und gegebenenfalls Original-Uhrzeit. Neuer Import **ersetzt** die vorherige Transaktions-CSV, verändert aber niemals Portfolio-CSV, Mein Trade oder Orders. Ohne Kurs, ISIN, Menge, Richtung, Datum oder Währung bleibt die Zeile unvollständig.
3. **DEGIRO-Bestätigungsmail:** Bisheriger geschützter Bob-AgentMail-Eingang mit optionalem PDF-Parser und signiertem Webhook. Original-Mails/PDFs werden nicht in den neuen CSV-Speicher kopiert; `/api/trade-email/read` liefert nur vorgeprüfte, reduzierte Belege, maximal die letzten 30. Die Weiterleitung aus dem eigenen Postfach muss vom Kontoinhaber eingerichtet werden; nur konfigurierte Absender werden angenommen.

## Wann wird abgeglichen?

Unter `Mein Trade → Positionsabstimmung · DEGIRO CSV + Bestätigungsmails` öffnen. Das Panel liest beim Öffnen die bereits gespeicherten Quellen und prüft den E-Mail-Eingang im geöffneten, sichtbaren Panel etwa alle 60 Sekunden. Nach neuem CSV-Import wird die lokale Auswertung sofort aktualisiert. Bei geschlossenem Browser empfängt der vorhandene Server nur bei korrekt eingerichteter Weiterleitung weiter E-Mails; ohne neue Portfolio-CSV kennt Bob keinen neuen Depotgesamtbestand.

## Matching und Sperren

- Gleiche gültige ISIN, eindeutiges BUY/SELL, positive ganze Stückzahl, tatsächlich beschrifteter EUR-Preis, Kalenderdatum, Sekundenuhrzeit, nur eine eindeutige CSV-Zeile je Beleg und `orderIdDigest` aus dem bestätigten Dokument.
- Doppelte identische Mails zu derselben Orderkennung zählen genau einmal.
- Gleiche Orderkennung mit widersprüchlichen Größen/Preisen/Zeiten kann verschiedene Teilfills bedeuten: `needs-review`, niemals stillschweigend zusammenzählen.
- E-Mail ohne Orderkennung oder mit unvollständigen Feldern → `needs-review`. CSV ohne Uhrzeit oder mit nur minutengenauer Zeit → lediglich `partialMatches`, keine falsche Präzision.
- Verkäufe werden als Verkäufe gezählt, nicht als Eröffnung eines Gold-SHORT-Produktes. Gleiches Zertifikat kann mehrere Käufe/Verkäufe und Teilfills enthalten.
- Ein E-Mail-Netto-Bewegungswert ist **kein** aktueller Depotbestand. Die Bestandszahl stammt ausschließlich aus der Portfolio-CSV. Selbst wenn beide Zahlen gleich sind, bleibt das ein **unvollständiger Indizienvergleich**: Es liegen maximal 30 Mails und kein belegter vollständiger Exportzeitpunkt vor.
- Neue Ausführungsmails nach der lokalen CSV-Importzeit veranlassen eine Warnung zur neuen Portfolio-CSV. Eine spätere Importzeit allein beweist nicht, dass die Datei nach dem letzten Trade exportiert wurde.
- Server-/Mailbox-Fehler dürfen nicht als bestätigte Nullposition angezeigt werden.

## Speicher und Sicherheit

Nur reduzierte Transaktions-CSV auf dem eigenen Gerät, keine Uploads von CSV-Daten an Bob/Render/Google Drive. E-Mail-Parser/Server bleiben unverändert. Neue Funktion ist eine reine Auswertung mit UI, **keine** automatische Bestandsmutation, Freigabe, Stop-Aktivierung oder Echtgeldorder. Keine neue Render-Datenbanktabelle und keine zusätzliche permanente Netzwerkanbindung. Eigener neuer Read-Only-JS-Pfad wird vom bestehenden Web-Server bereitgestellt.

## Abnahme

`node test_degiro_position_reconcile.js` testet eindeutige Paare, doppelte Mails, konfligierende Order-IDs, fehlende Kennung, eine sekundengenaue bzw. ungenaue Zeit, Zeitumrechnung, vorhandene/fehlende CSVs, negative SALE-Mengen, fehlerhafte Eingaben und den expliziten Verzicht auf brokerseitige Bestandsbehauptungen.

Geräte- und Ende-zu-Ende-Prüfung mit echtem DEGIRO-CSV-Layout und tatsächlicher (zulässig weitergeleiteter) E-Mail ist noch gesondert nötig. Keine Original-Mail mit Kontonummer oder Adresse in GitHub-Issues, öffentlichen Logs oder Screenshots veröffentlichen.
