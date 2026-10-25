# Bob – Handy: Ein-Klick-Link für harmlose Anzeige-Aufträge

## Nutzerziel

**Ohne erneuten STOPP-Test und ohne zweiten Bildschirm** soll ein bewusst
angetippter Link aus ChatGPT auf demselben Samsung den richtigen Bereich in
**Bob – Handy** vorbereiten. Der Benutzer bestätigt anschließend wie bisher
mit **„✅ Geteilten Anzeigeauftrag einmalig öffnen“**.
Eine bewusst geöffnete und streng erlaubte HTTPS-Adresse darf in der neuen
stabilen App unmittelbar **eine feste Bob-Webansicht** öffnen. Custom-Scheme-
und Kopieraufträge benötigen weiter die Bestätigung. Keine Brokeraktionen,
Ordermasken oder frei wählbaren URLs.

### Erste Links (vorbehaltlich Samsung-/ChatGPT-Gerätetest)

- Goldprodukte: \`bobhandy://handoff/OPEN_PRODUCTS\`
- Goldmarkt: \`bobhandy://handoff/OPEN_MARKET\`
- Mein Trade (Ansicht): \`bobhandy://handoff/OPEN_TRADE\`
- Simulation (Ansicht): \`bobhandy://handoff/OPEN_SIMULATION\`

Der Link nutzt das Android-Intent-System. ChatGPT-/Browser-Clients dürfen
solche nicht-http(s) Links blockieren; dann bleibt die **bereits getestete**
Alternative **„📋 Kopierten ChatGPT-Auftrag prüfen“** verfügbar. Das ist
keine authentifizierte Push-Nachricht von ChatGPT und kein Live-Fernzugriff.
**Der Benutzer muss den Link selbst öffnen.**

## Sicherheitsgrenzen

1. Es gibt **keinen** neuen Netzwerk- oder Bedienungshilfen-Zugriff für die
   App. Keine Server-Postfächer, Tokens oder privaten Inhalte im Link.
2. Ein benutzerdefiniertes URI-Schema ist nicht exklusiv an unsere App gebunden:
   fremde Apps könnten es ebenfalls registrieren. Deshalb enthält ein Link
   ausschließlich die **öffentliche Kennung einer ungefährlichen Seite**,
   keine Geheimnisse, Kontodaten, Signaturen oder Kursinformationen.
3. Sämtliche externen Intents sind unvertrauenswürdig. Vollständige,
   kanonische Syntax erforderlich; Fragment, Query, Port, Userinfo,
   Kodierungen, mehrere Schritte oder alle nicht erlaubten Aktionen werden
   abgewiesen. Frei übergebene Webseiten, Einstellungen, Broker-Apps,
   OCR-Bilder und Echtgeldorders sind ausgeschlossen.
4. Der bestehende örtliche Einmalfreigabe-Mechanismus mit maximal 60 Sekunden
   Gültigkeit prüft **alle Text- und Custom-Scheme-Aufträge**.
   Allein der ausdrücklich angeklickte HTTPS-Link darf unmittelbar eine
   fest zugeordnete, rein lesende Bob-Webseite starten. STOPP/App-Wechsel
   verwirft weiterhin alle ausstehenden Freigaben.
5. Die bestehende lokale \`SHARE_PREVIEWED\`-/\`SHARE_REJECTED\`-/\
   \`SHARE_APPROVED\`-Protokollierung bleibt erhalten, ohne Linkinhalte.
6. Erst ein **realer Samsung-Test** kann bestätigen, dass die ChatGPT-App
   diese benutzerdefinierten Links tatsächlich an Android weiterleitet.
   Ein CI-Erfolg bestätigt nur Build und Prüflogik.

### Frühere Perspektive (historisch)

Für wirklich geräte-verifizierte \`https\`-App-Links müsste die
Eigentümerdomäne mit \`/.well-known/assetlinks.json\` und dem richtigen,
signierten Android-Zertifikat verknüpft werden. **Nicht** öffentlich
eingerichtet und **nicht** Teil dieses Schritts, um ohne verifizierte
Domänenbindung keinen unzuverlässigen HTTPS-Handler zu installieren.


### Aktualisierung: HTTPS-Anzeige ohne Kopieren (25.10.2026)

HTTPS-Links wie
`https://bob-private-scanner.onrender.com/handy/OPEN_PRODUCTS`
sind im aktuellen Code auf einen direkten Start der festen Bob-Webseite
ausgelegt. Android muss den Link mit dem installierten stabilen Paket
verbinden; ob ChatGPT ihn weiterleitet, kann nur das Samsung-Gerät zeigen.

Falls eine Browserseite statt Bob erscheint, dort
**„Bob direkt im Browser öffnen“** tippen. Der alte Custom-URI-Link,
Android-Teilen und die sichere Kopierfreigabe bleiben separat bestehen.
Das ist kein authentifizierter Fernauftrag und keine Orderfreigabe.
