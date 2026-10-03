# Produktpush

„Marktsignale“ (`general`) ist der einzige Schalter für Produktfreigaben und deren Rücknahme. `trade` und `activeTrade` schalten diese Meldungen nicht frei. Neue Auswahlen werden bei geöffneter Bob-App aus den dort verfügbaren, vom Nutzer bestätigten Produktnachweisen geprüft. Produktpushs benötigen die Web-Push-Registrierung; ntfy und allgemeine Push-Aufrufe dürfen diese Prüfung nicht umgehen.

## Prüfung und Versand

- Die App übermittelt höchstens zwölf Produktdatensätze, Markt-Kontext, Quellenzeiten und Nachweise, niemals eine verbindliche Freigabe.
- Der Push-Service führt `selectionWorkflow` aus derselben `degiro_assistant.js` unter Node erneut aus. `approved`, Titel und Rangfolge aus einer Anfrage haben keine Wirkung. Screenshotbestätigungen bleiben Nutzernachweise, keine unabhängige Emittenten-Zertifizierung.
- Serverzeit ersetzt die Client-Prüfzeit. Zusätzlich müssen Anfrage, Spotreferenz und Historienstatus aktuell sein. Dieselben Pflichtdaten-, Faktor-, Richtungs-, Kontrakt-, KO- und Unsicherheitsprüfungen gelten wie in der Anzeige. Spread und Hebelhöhe erhalten keine neue Gewichtung.
- Freigaben gelten höchstens 30 Sekunden und nie länger als ihre Nachweise. Unter fünf Sekunden verbleibender Gültigkeit erfolgt keine Empfehlung. Die Push-TTL sowie die Empfangsprüfung verhindern verspätete Empfehlungen.
- Ausschließlich das anfragende Abonnement wird benachrichtigt. `general_enabled=TRUE` wird unmittelbar vor Versand mit Zeilensperre geprüft; Deaktivierung löscht den gespeicherten Auswahlzustand. Der Service Worker unterdrückt auch bereits eingereihte Produktmeldungen nach dem Ausschalten.

## Meldungen und Ablauf

ISIN, Richtung und Basiswert bilden die Auswahlidentität. Kursänderungen oder eine andere Reihenfolge derselben Produkte erzeugen keinen weiteren Push. Neue Produkte oder Richtungen werden gemeldet; weggefallene Produkte nennt die geänderte Auswahl. Dieselbe Auswahl wird nach einer Rücknahme frühestens nach fünf Minuten erneut angekündigt.

Eine zuvor gemeldete Auswahl erhält bei Wegfall der Freigabe einmal einen Rücknahmehinweis. Der Service prüft alle 15 Sekunden auf abgelaufene Bestätigungen, auch wenn die App geschlossen wurde. Eine unveränderte offene App erneuert die Prüfung alle zehn Sekunden. Ohne aktuelle Prüfung entstehen keine neuen Freigaben. Schlafende kostenlose Dienste und Gerätezustellung können Hinweise verzögern; es gibt keine Zusicherung lückenloser Hintergrundüberwachung.

Zustand und Entdopplung liegen im vorhandenen PostgreSQL-Abonnement. Fehlgeschlagener Versand verbraucht die Meldung nicht. Es werden keine neuen Dienste angelegt, keine Orders ausgelöst und keine Live-Testempfehlungen versendet.

## Tests

`test_selection_flow.js`: 0/1/2/3 Produkte, Pflichtdaten, neutrale/widersprüchliche Signale, Futures-Kontrakt und Unsicherheit, Ablauf der Nachweise, gemeinsame Serverprüfung.

`test_selection_push.js`: Ein/Aus, Ausschalten während Vorbereitung, Wiederholung, verspätete Zustellung und Service-Worker-Sperre.

`test_product_push.py`, `test_push_monitor.py`: Übergänge, Rücknahme, Wartezeit, geschützter Endpunkt, gerätebezogener Versand, erneute Schalterprüfung und Fehlerbehandlung.
