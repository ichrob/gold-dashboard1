# DEGIRO 2 – manuelle Handy-Übergabe

Unter Mehr → DEGIRO 2: vorhandene Produktidentitäten aus Bob übernehmen,
aktuelles Produktlimit und Gebühren eingeben, Tagesbudget setzen und auf Wunsch
die rechnerische maximale Kaufstückzahl ermitteln. Diese Obergrenze ist keine
Empfehlung, das Budget auszuschöpfen. Entwürfe speichern, ISIN oder Ordertext
kopieren, DEGIRO öffnen und jeden echten Auftrag selbst prüfen und bestätigen.

Die Android-Intent-Verknüpfung ist eine bestmögliche App-Öffnung mit Web-Fallback.
Keine Android-Installation, keine Zugangsdaten, keine Accessibility-Rechte,
keine zusätzlichen API- oder Lizenzkosten. Kein automatisches Ausfüllen oder
Bestätigen in DEGIRO. Es gibt keinen versteckten Echtgeldmodus.

Budget: summiert lokal geplante Käufe inklusive eingegebener Gebühren. Verkäufe
schaffen kein neues Planbudget. Tagesgrenze Europe/Zurich; ältere Entwürfe werden
bei einer neuen Tagesplanung ersetzt. Nur aktueller Browser, keine Kontosynchronisation.
Entwurf entfernen ist keine Stornierung einer echten Order. Es wird keine reale
Ausführung erkannt. Budget ist keine Verlustgrenze. Preise max. zwei Dezimalstellen;
abweichende Tickgrößen und Orderregeln müssen direkt bei DEGIRO geprüft werden.

Prüfung: node test_degiro_handoff.js; node validate_bob.js;
node test_zukunft_navigation.js; python -m py_compile server.py.
Android-Start und Zwischenablage müssen auf dem Nutzergerät überprüft werden.
