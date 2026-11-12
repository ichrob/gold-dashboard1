# Bob: automatische Studienfehler → KI-Wächter → optionaler Gemini-Review

Stand 11. November 2026; Anlass [#1542](https://github.com/ichrob/gold-dashboard1/issues/1542).

## Ein vorhandener Meldeweg statt paralleler Reparaturagenten

1. **Papier-Forschungsworker** (`research_restart.py`) führt die bestehenden Originaldatenprüfungen unverändert durch und bewahrt pro Lauf maximal 64 neue Qualitätsbeobachtungen für höchstens 20 Minuten sowie maximal 64 nach Einführung der Originalpolitik `original-observed-over-90s-v2` abgeschlossene Fälle für höchstens vier Stunden auf. Die alten kumulativen Ergebnisse bleiben unverändert und lösen keine neuen Vorfälle aus.
2. **Push-Service** (`push_server.py`) liest eine bereits indexierte Forschungssteuerzeile im vorhandenen öffentlichen `/health`-Aufruf. `bob_study_health.py` projiziert ausschließlich `status`, `scope`, `codes`, `readOnly`, `realOrders`. Keine internen Preise, ISINs, Originalbeobachtungen, Kontendaten oder Worker-Fehlertexte.
3. **Bestehender GitHub-Watchdog** (`bob_issue_watchdog.py`) nimmt nur `studyHealth` mit exakt passendem Scope und festen Codes an. Die Handelszeit muss aktiv sein. Zwei unabhängige, 15 Sekunden getrennte Gesundheitsproben müssen denselben Code zeigen. Bestehende Titel-/Issue-Deduplizierung verhindert Doppelvorgänge; ein alter kumulativer Fehler erzeugt kein neues Issue.
4. **Die bestehende KI-Koordination** (`bob_ai_coordination.py`) ergänzt zu neuen offenen Fällen maximal drei idempotente, öffentliche Übergabekommentare je GitHub-Lauf mit Code, möglichem Prüfpunkt und einziger ChatGPT-Reparaturverantwortung. Dies ist eine **Aufgabenübergabe**, keine Garantie, dass ein fremder ChatGPT-Dialog gestartet oder ein PR erstellt wurde.
5. **Gemini**: Der vorhandene `bob-gemini-free-review.yml`-Workflow bleibt optional und beschränkt auf öffentliche gefilterte PR-Diffs. Er darf nur mit bestätigter kostenloser Konfiguration und API-Zugriff arbeiten. Ohne tatsächlich überprüften PR-Kommentar heißt sein Status ausdrücklich **nicht überprüft**. Weder private Diagnosen noch Secrets, Orders oder automatische Codeübernahme erfolgen über Gemini.

## Fest definierte Schwellen

- `study-original-input-degraded`: mindestens zwölf neue Originalprüfungen innerhalb von 20 Minuten, mindestens sechs ungültig, mindestens 25 % ungültig, davon mindestens zwei in den letzten fünf Minuten.
- `study-outcome-coverage-degraded`: mindestens fünf **neue**, nach `original-observed-over-90s-v2` beendete Originalfälle in vier Stunden, mindestens vier unentscheidbar und mindestens 60 % unentscheidbar, davon ein neuerer Fall in den letzten 45 Minuten.
- `study-worker-stale`: während einer tatsächlichen Handelszeit ist die aktuelle aktive Qualitätsstudie länger als drei Minuten nicht überprüft worden.

Alle drei Kategorien sind Warnungen für Untersuchung. Sie beweisen weder entgangenen Gewinn noch einen Codefehler oder die Verantwortung eines konkreten Anbieters. Für einen Warncode muss eine frische Studiensteuerung vorliegen; `paused`, `unavailable`, `inactive` und fehlende Werte beweisen nie eine Erholung. Studienwarnungen werden wie Produktnachweisvorgänge **nicht automatisch geschlossen**, wenn ein bloßer Code verschwindet; die abschließende Original-Abnahme bleibt unter #1541 / dem zuständigen Einzelissue.

## Sicherheitsgarantien und Abnahme

- Keine Änderungen an Bobs Produktfreigaben, KO-Abstand, Gebührenmodell, Stops, Simulationsein- und -ausstiegen, Marktsignalen oder echten Brokerorders.
- Kein öffentliches Exportieren privater Diagnosewerte, Kurszeiten oder Produkttabellen.
- Die nächsten Arbeitsschritte bleiben GitHub-Prüfung, möglicher klarer Patch, vollständige CI und unabhängiger Render-Live-Nachweis.
- Die Tests prüfen alte kumulative Werte, neue und einmalige Fehler, anhaltende Fehler, Nachtpause, veraltete/fehlende Beobachtungen, unbekannte Code-Injektion, sichere Nicht-Schließung und unverfälschte originale Fallhistorie.
- Nach Veröffentlichung die neuen `studyHealth`-Felder an **beiden** Diensten und den GitHub-Wächterlauf prüfen; ohne live bestätigten Vorfall darf man keine tatsächliche KI-Reparatur behaupten.

## Bewusst noch nicht automatisiert

Das Eröffnen eines ChatGPT-Gesprächs durch die Handy-Share-Funktion wird weiterhin nur vom Nutzer angestoßen. Eine lokale Android-App darf nicht heimlich in fremde ChatGPT-Konversationen schreiben. Der GitHub-Weg ist die automatisierte Übergabe **innerhalb Bobs bestehender GitHub-Prozesse**, kein Beweis einer ausgeführten ChatGPT- oder Gemini-Reparatur.
