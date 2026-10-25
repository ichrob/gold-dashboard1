# Diagnoseziel 17 – Warteschlangen und Verluste (Teilnachweis)

Stand: 25.10.2026. **Status weiter `partial`, nicht einzeln als abgeschlossen zählen.**

Bobs Hintergrund-Evaluator hat eigene Prozesszähler (`completed`, `failed`, `queueTimeouts`, `waiting`, `inFlight`). Der asynchrone Diagnoseverlauf meldet separat `stored`, `dropped`, `failures` und `queued`. Die Lesesperre vor Datenbank-Berichten (`report_admission`) hatte bislang **keine** vom autorisierten Bob-Lesezugriff erreichbaren Warteschlangen-Zähler.

Die neue reine Momentaufnahme `report_admission.status()` meldet ausschließlich aggregierte, prozesslokale Zähler für gleichzeitige laufende Report-Loads, vorgemerkte Report-Keys, Abschluss/Fehler, begrenzte Kapazitäts-Timeouts, überfüllte Anfragewarteschlange sowie zusammengeführte gleiche parallele Leseanfragen. Weder Report-Key, Query, Request-Parameter, Token, SQL-Parameter noch private Resultate erscheinen im Status. Der bisherige `report_admission.read`-Ablauf, die maximale parallele Lesekapazität (zwei) und die bestehende Überlaufgrenze (32 eindeutige Anfragen) bleiben unverändert. Der Zähler `queueFull` beschreibt **abgewiesene Leseanfragen**, nicht verlorene Markt- oder Push-Signale.

Die Daten werden in `bob_diagnostics.push_snapshot` als `reportAdmission` mit der bereits bestehenden privaten MCP-Leseberechtigung ausgegeben. Kein neuer öffentlicher Endpunkt, kein neuer Datenbankzugriff, keine geänderten Credentials, kein Aufweichen des Abbruchs bei Fehlern. Die Testdatei `test_diagnostic_report_queue_status.py` belegt neben Zählung und Warteschlangen-Grenzwerten die Geheimnisfreiheit, fehlende Nebeneffekte, zusammengeführte Abfragen und die Trennung von Push-Geräteempfang.

**Abnahme fehlt weiterhin:** echte, autorisierte gleichzeitige Report-Anfragen mit gemessenen Quelle-/Zeitstempeln nach Produktivdeployment; CI allein belegt nicht, dass bei realen Render-Pools keine Anfragen fehlen. Ebenso ist das Vorliegen einer Push-Subscription kein Empfangsbeleg. Ohne die Originalbeobachtung dürfen wir keine verschwundenen Berichte oder behobenen Queue-Stau bestätigen.

Der Gesamtstand der 100 Einzelabnahmen bleibt bis zu neuen Originalnachweisen **2/100**. Keine Echtgeldorders oder automatischen Handelsfreigaben.
