# Diagnoseziel 15 – HTTP-Fehler je Endpunkt (Teilnachweis)

Stand: 25.10.2026. **Keine Einzelabnahme, Status bleibt `partial`.**

Die bisherige Render-Stichprobe vom 25.10.2026 (10:00–11:20 UTC) enthielt aggregierte HTTP-Statuscodes für zwei Dienste; sie belegte **nicht** den verursachenden Endpunkt pro Fehler und keine vollständige kontinuierliche Log-Abdeckung.

`diagnostic_http_endpoint_errors.classify` klassifiziert **explizit übergebene, zeitgestempelte Render-Requestlog-Stichproben** eines Dienstes. Es gibt nur 1xx–5xx-Zählungen und den Namen bekannter **statischer** Routen zurück. Unbekannte Routen, dynamische Kennungen und URL-Query-Parameter werden zu `other-unclassified` zusammengefasst. Ein 401/403 bleibt eine Zugriffsablehnung, keine nachgewiesene Serverstörung. Ein 5xx beweist keinen Neustart oder Datenbankfehler. Höchstens 250 Proben pro Auswertung, Folgeseiten erzwingen `sampleTruncated=true`.

**Grenzen und nächste Abnahme:** Der Code ruft Render nicht selbst auf und kennt keine externen Credentials. Es gibt keine Behauptung über Originalität oder Vollständigkeit der vom Aufrufer eingespeisten Werte: `liveVerified=false`, `completeTrafficProven=false`. Für die Einzelabnahme sind zusätzlich zwei datierte autorisierte Originalabrufe der Render-Requestlogs (Scanner/Push) einschließlich Pagination, ein vollständiger Commit-/CI-Abgleich und ein unabhängig beobachteter Produktivtest erforderlich. Mit dem aktuell verbundenen Render-Werkzeug muss zuvor der Workspace ausdrücklich bestätigt werden.

Testdatei: `test_diagnostic_http_endpoint_errors.py`. Tests behandeln 2xx, 4xx, 5xx, Datenschutz, Fehlerfall, Originalzeit und Abbruch bei unvollständigen Proben. Der 100er-Zähler bleibt bis zur vollständigen End-to-End-Evidenz bei **2/100**. Keine Echtgeldorders, keine neuen Render-Ressourcen oder Datenbankrechte.
