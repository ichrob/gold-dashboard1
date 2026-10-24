# Samsung-Fernkopplung – sichere, manuelle erste Stufe

**Status:** Implementiert auf einem separaten GitHub-Entwicklungszweig; ein Android-CI-Lauf
beweist weder eine erfolgreiche Installation noch eine echte Samsung-Fernverbindung.
Ein automatischer Netzwerkkanal ist **nicht** eingebaut. Die App behält ihren
explizit gesperrten Netzwerk- und Accessibility-Zugriff.

## Sicherheitsmodell

- **Ausgangslage gesperrt:** Nach Start/Neustart ist keine Kopplung aktiv.
  Nur ein sichtbarer Tastendruck auf Samsung erzeugt eine temporäre 256-Bit-HMAC-Sitzung.
- **Bewusste Kopplung:** Der Besitzer darf die geheime Einladung per Android-Teilen
  an ein **eigenes, vertrauenswürdiges** Zweitgerät senden. Niemals Schlüssel in
  ChatGPT, GitHub, Logs, Screenshots oder Support-Nachrichten einfügen.
- **Transport ohne Hintergrundzugriff:** Das Zweitgerät öffnet die Datei
  \`android_companion/remote_sender.html\` lokal und signiert einen einmaligen
  Auftrag. Der Besitzer teilt diese signierte Zeichenfolge anschließend über
  die Android-Teilen-Funktion an Bob-Handy oder fügt sie bewusst dort ein.
  Diese Stufe kann **keinen** Zugriff aus der Ferne ohne Benutzerinteraktion herstellen.
- **Kryptografischer Schutz:** HMAC-SHA256 über Version, Sitzungskennung,
  Unix-Zeit in Millisekunden, Zufallsnonce und erlaubte Aktion. Syntax strikt,
  höchstens 2 Minuten alt, 30 Sekunden Zukunftstoleranz, Nonce nur einmal nutzbar.
  Freigabe höchstens 60 Sekunden nach erfolgreicher Signaturprüfung,
  Sitzungsdauer höchstens 30 Minuten nach monotonic elapsedRealtime.
- **Berechtigungen:** Nur fest definierte Anzeige-Links der eigenen Bob-Webseite
  (Produkte, Goldmarkt, Mein Trade, Simulation, Forschung, Lernen).
  Kein beliebiger URL, kein Klicken in DEGIRO, keine Formulare, keine Tastatureingaben,
  keine Bildschirmaufnahme, keine Bestellungen, kein Trading.
- **Jeder Auftrag benötigt eine neue Freigabe** per lokalem Button. Importieren oder
  Prüfen allein führt nichts aus. Beim App-Wechsel wird die Freigabe verworfen.
  Auch ein verifizierter Befehl darf nie eine Folgekette auslösen.
- **STOPP** sperrt alte Sitzungen und verwirft Schlüssel, Wiederholungsschutz und
  noch nicht erlaubte Aufträge. **Widerruf** bewirkt dieselbe Entwertung.
  Beide funktionieren ohne Internet. Eine bereits geöffnete Browserseite
  kann dadurch nicht rückgängig gemacht werden.
- **Protokoll:** maximal 80 lokale, erlaubnisarme Ereignisse mit Uhrzeit,
  Ereignistyp und harmlosem Aktionstyp. Keine Tokens, MACs, Texte, Bilder,
  Login-/Broker-/Depotdaten, keine automatischen Übermittlungen.

## Vorbereitete sichere Abnahme

1. In „Bob – Handy“ ohne Freigabe signierten Befehl importieren:
   abweisen, keine Seite öffnen.
2. Kopplung bewusst freigeben, Einladung **nur** auf eigenem Zweitgerät verwenden,
   mit \`remote_sender.html\` signieren, auf Samsung importieren: zunächst
   nur Vorschau. **Erst** nach eigener Bestätigung eine erlaubte Bob-Anzeige.
3. Wiederholung desselben Auftrags, manipulierte Signatur, falsche Aktion,
   alte Zeit und unerlaubte Brokeraktion müssen abgewiesen werden.
4. Während einer Vorschau STOPP drücken und nochmals Ausführen versuchen:
   nichts darf starten. Danach alte signierte Nachrichten zurückweisen.
5. Neu koppeln und sofort widerrufen: derselbe Effekt.
6. App verlassen oder neu starten: keine ausstehende Ausführung; Neustart
   verliert außerdem den geheimen Sitzungsschlüssel.
7. Lokales Protokoll öffnen: Ereignisse sichtbar, keine Kopplungsschlüssel.
8. Prüfen, dass **INTERNET** und **BIND_ACCESSIBILITY_SERVICE** im finalen APK
   nicht vorhanden sind. Keine DEGIRO-Funktionen oder Echtgeldorders.

## Noch nicht fertig

Eine wirklich unbeaufsichtigte, netzbasierte Fernkopplung aus ChatGPT/Render
zum Samsung gibt es **absichtlich noch nicht**. Dafür bräuchte es einen separat
authentifizierten und sicherheitsgeprüften Transport (z. B. gegenseitiges
Gerätevertrauen, Ende-zu-Ende-verschlüsselte Nachrichten, Nutzereinwilligung,
Server-Sperre/Widerruf und öffentliche Sicherheitsprüfung). Diese Erweiterung
darf das lokale Einmalfreigabe- und STOPP-Modell **nicht** umgehen. Die
Einladung ist ein Geheimnis und darf auch künftig niemals serverseitig geloggt
oder in öffentlichen URLs verwendet werden.
