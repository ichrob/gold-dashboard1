# Bob – Handy: Ein-Klick-Link für harmlose Anzeige-Aufträge

## Nutzerziel

**Ohne erneuten STOPP-Test und ohne zweiten Bildschirm** soll ein bewusst
angetippter Link aus ChatGPT auf demselben Samsung den richtigen Bereich in
**Bob – Handy** vorbereiten. Der Benutzer bestätigt anschließend wie bisher
mit **„✅ Geteilten Anzeigeauftrag einmalig öffnen“**. Es wird **niemals**
automatisch eine Webseite, ein Broker, eine Ordermaske oder eine andere
App ausgeführt.

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
   Gültigkeit prüft **jede** Aktion. STOPP/App-Wechsel verwirft sie.
   Es gibt **keine** automatische Ausführung aus einem Link.
5. Die bestehende lokale \`SHARE_PREVIEWED\`-/\`SHARE_REJECTED\`-/\
   \`SHARE_APPROVED\`-Protokollierung bleibt erhalten, ohne Linkinhalte.
6. Erst ein **realer Samsung-Test** kann bestätigen, dass die ChatGPT-App
   diese benutzerdefinierten Links tatsächlich an Android weiterleitet.
   Ein CI-Erfolg bestätigt nur Build und Prüflogik.

### Perspektive

Für wirklich geräte-verifizierte \`https\`-App-Links müsste die
Eigentümerdomäne mit \`/.well-known/assetlinks.json\` und dem richtigen,
signierten Android-Zertifikat verknüpft werden. **Nicht** öffentlich
eingerichtet und **nicht** Teil dieses Schritts, um ohne verifizierte
Domänenbindung keinen unzuverlässigen HTTPS-Handler zu installieren.
