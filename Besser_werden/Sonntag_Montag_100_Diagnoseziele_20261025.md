# Bob – 100 Diagnoseziele: Sonntagsvorbereitung und Montags-Abnahme

Stand 25.10.2026. Code/CI und laufende Einzelabnahmen sind verschieden. Im strengen Register stehen **3/100** (Ziele 8, 13, 18), 91 sind teilweise vorbereitet, 5 erfordern echte Samsung-Tests, 1 ist durch die angebundene Client-Werkzeugbeschreibung blockiert.

## Was heute prüfbar ist und was Originalbelege erfordert

| Zielbereich | Sonntag: unabhängig von geöffnetem Börsenhandel | Fehlender Originalnachweis |
|---|---|---|
| 1–10 Diagnose | Code, Module, Quellen-/Zeittrennung, historische Health-Vergleiche, Privacy-/Negativtests, CI | Ziel #1 benötigt unterstützte focus-Eingabe in verbundener MCP-Client-Werkzeugbeschreibung; Korrelation und Gesamtstatus erfordern punktbezogene Originalbelege |
| 11–20 Render/Worker | Archiv-/Fehlerproben, reale CPU-/RAM-Metriken, Neustart-/Queue-Grenzen, CI/Render-Build, sichere Diagnose | Echte 30-Sekunden-Zyklen, tatsächlich ausgeführter Neustart, ursprüngliche Ursache und 30-Tage-Audit-Queryplan |
| 21–30 Goldmarkt | Historische Originalzeiten, Quellenprüfung, Backfill-/Weekend-Regression | Frischer Spot/CFD/FX, Zeitsynchronisierung und Original-Kerzen bei aktiver Marktdatenlieferung |
| 31–40 DEGIRO-Produkte | CSV-/Screenshot-Archiv, OCR-Identität, Quellzuordnung, Fail-closed-KO/Emittententests | Datierte frische Geld-/Brief-/Hebel-/KO-/Broker-Ausführungsnachweise |
| 41–50 Signale | Eingefrorene historische Indikator-, Ranking-, Push- und Einstiegsschutztests | Neue rechtzeitige Originalpreise, späterer überprüfbarer Ziel-/Stop-/Signalausgang |
| 51–60 SnapTrade | Bereits autorisierte rein lesende Historie, Deduplizierung, FIFO-/FX-/Gebühren-Qualitätsprüfungen | Aktuelle separate Broker-/Emittentenkurse und Vollständigkeit; SnapTrade-Depot ist kein DEGIRO-Ausführungskurs |
| 61–70 Mein Trade | Historische manuelle Eingaben, KO-/Stop-/Push-Versuche, Provenienz und Kosten logischer Tests | Reale spätere Produktpreise, tatsächlicher Android-Push-Empfang und Originalausführungen |
| 71–80 Simulationen | Fünf gespeicherte Profile, Kostenannahmen, 13 unklare Fälle, verknüpfte Datenlücken-/Paper-Tests | Neue echte Paper-Worker-Eingaben und zeitlich passende unabhängige Originalpreise; Nachberechnung ist kein damaliger Fill |
| 81–90 MCO-Forschung | Öffentliche Originalvideo-Metadaten/Untertitel, zulässige Frames, Forschungs- und Schattenregeln | Fehlende Mitglieder-Videos/Frames und ausreichend neue, gepaarte Standard-/Stresstests |
| 91–95 Samsung | Signatur, lokale App-Code-/Browser-Sicherheit und Mock-Tests | Freiwillige Verifikation auf realem Samsung: Version, Stimme, STOPP, Bilderteilen, Navigation; nicht heimlich testbar |
| 96–100 Fehler-Übergabe | GitHub-Dedupe, Tests, Audit, Rollback/Security-Prüfungen ohne Kontoaktion | Echte ChatGPT-Handoff-/Neustart-/Reparaturketten mit unabhängiger Bestätigung |

## Sonntagsbeobachtung: erfasste und nicht erfasste Übergaben

Read-only private Bob-Diagnose 25.10.2026 ca. 19:58 UTC: begrenzte 7-Tage-Stichprobe mit max. 20 Archivereignissen je Typ. Push-Entscheidungscaptures vorhanden, aber **keine** push-delivery-Captures und **keine** paper-input-Captures in der aktuellen Stichprobe. Der Paper-Worker war im Wochenendmodus pausiert. Das beweist **weder** fehlgeschlagene Push-Nachrichten **noch** fehlende Simulationen. Auch zwei vorhandene Typen ohne identische Trace-/Quellzeit beweisen **keine** gemeinsame Übergabe. Neue Lesediagnose diagnosticCaptureHandoff macht genau diese Trennung explizit.

## Montag, 26.10.2026, ab 08:00 Uhr Zürich

Die einmalige automatische Montags-Liveprüfung ist bereits eingerichtet. Sie soll Originalquellen/-uhrzeiten, aktive Worker-Zyklen, echte Paper-Inputs, zeitnahe Produktwerte und unverbundene Push-Versuche nur über autorisierte vorhandene Lesetools kontrollieren. Falls Anbieter um 08:00 Uhr noch keine frischen Kurse liefern, bleiben diese Ziele ausdrücklich **ausstehend**. Keine Rekonstruktion fehlender damaliger Originalkurse aus neueren Preisen.

**Schutz:** keine Echtgeldorders, keine automatischen Handelsfreigaben, keine E-Mails, kein Öffnen der Produktionsdatenbank-IP-Allowlist, keine privaten Depotdaten in GitHub. CI/Mocks sind technischer Beleg, aber keine Vollabnahme echter Markt-/Geräteereignisse.
