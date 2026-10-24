# Bob – Handy: normale HTTPS-Links auf demselben Samsung

## Erreichte Stufe

Ein normales, anklickbares HTTPS-Ziel auf Bobs eigener Website bietet einen
**manuellen Knopf zur Übergabe an „Bob – Handy“**. Es ist noch KEIN direkt
automatischer ChatGPT-Push und noch KEIN mit Android verifizierter App Link.

Beispiel (Gold-Hebelprodukte):

https://bob-private-scanner.onrender.com/handy/OPEN_PRODUCTS

Ablauf auf dem **einen** Samsung:

1. Den HTTPS-Link im Chat antippen. Die Website setzt die bestehende Bob-
   Anmeldung voraus. Falls sie abgelaufen ist, wird die normale Anmeldeseite
   geöffnet und danach die bekannte Bob-Ansicht zugänglich.
2. Im Browser auf **„Bob – Handy öffnen“** tippen. Android *kann* daraufhin
   die App öffnen; die Unterstützung hängt vom Browser ab. Wenn Android
   nachfragt, bewusst die richtige App **„Bob – Handy“** auswählen.
3. In Bob – Handy eine harmlose Anzeige-Vorschau lesen; nur wenn gewollt
   **„✅ Geteilten Anzeigeauftrag einmalig öffnen“** tippen.
4. Die Anzeige öffnet sich in Bob. Ohne App-Öffnung bietet die Webseite
   den alternativen Knopf **„Stattdessen Bob im Browser öffnen“** an.

## Sicherheitsgrenzen

- Öffentlich abrufbare persönliche Inhalte: **keine**. Ohne Bob-Anmeldung
  liefert der Handoff-Pfad nur die normale Anmeldung, kein persönliches
  Protokoll oder Freigabeschlüssel.
- Das HTTPS-Ziel hat weder geheime Anmeldedaten noch eine Freigabeberechtigung.
  Keine Session-ID, OTPs, Signaturschlüssel, ISINs oder Depotdaten im URL.
- Genau neun vorgegebene Bob-Anzeigen. Alle unbekannten URLs, Parameter und
  Trader-/Brokeraktionen werden vollständig abgewiesen.
- Die Hand-off-Seite besitzt kein JavaScript, keine automatische Weiterleitung,
  keine unsicheren Drittanbieter-Ressourcen, Cache-Control: no-store,
  eingeschränkte CSP und Referrer-Policy: no-referrer.
- Auf dem Android bleibt der vorhandene **einmalige manuelle Freigabeschritt**
  mit 60-Sekunden-Frist und **NOT-STOPP**. Kein zusätzlicher Android-Zugriff,
  kein dauerhafter Hintergrundkanal, keine Echtgeldorders.
- Android Custom-URI bobhandy:// ist **nicht** exklusiv abgesichert.
  Deshalb enthält er nur eine ungefährliche Anzeige-ID. Nur die originale,
  vom Nutzer installierte App darf bewusst ausgewählt werden.
- **Kein echter Samsung-Test** allein durch erfolgreiches GitHub-CI:
  Der Browser kann das URI-Schema blockieren; dann gilt der sichere
  Browser-Fallback. Das bestehende Kopieren bleibt ebenfalls möglich.

## Nächste Stufe: verifizierte HTTPS App Links

Für ein direktes Android-Aufrufen mit einer Berührung benötigen wir eine
öffentliche, vom Android-System geprüfte Zuordnung via
https://bob-private-scanner.onrender.com/.well-known/assetlinks.json,
der festen Paketkennung ch.bob.degirocompanion.stable und dem
**öffentlichen SHA-256-Zertifikatsfingerabdruck** der tatsächlich signierten
Release-APK. Noch **nicht** eingerichtet. Der private APK-Signaturschlüssel,
Passwörter und personenbezogene Inhalte dürfen nie veröffentlicht werden.
