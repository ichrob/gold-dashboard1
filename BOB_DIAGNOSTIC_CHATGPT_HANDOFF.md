# Bob → ChatGPT: sichere Fehlerdiagnose ohne Kopieren

## Ziel
Auf dem Samsung zuerst Bob/Probleme öffnen, dann über den Button **„Fehlerdiagnose an ChatGPT teilen · ohne Kopieren“** das Android-Teilen-Menü aufrufen. Nur nach bewusster Auswahl von ChatGPT und dortigem **Absenden** wird ein Bericht an die Unterhaltung übertragen.

## Zwei getrennte Wege
1. **Technische Störungen:** Unter Bob → Probleme (auch direkter HTTPS-App-Link `/handy/OPEN_PROBLEMS`) enthält der Bericht maximal 20 freigegebene Fehlercodes, GitHub-Issue-Nummern und Status sowie aggregierte Reparaturzähler. Bei stale/unavailable wird dies ausdrücklich genannt; die Leere eines Ausfalls zählt nie als Fehlerfreiheit. Der Bericht wird lokal im Browser erzeugt und nicht im Server für ChatGPT zwischengespeichert.
2. **Gold-Hebelprodukt-Probleme:** Im Produktbereich bleibt die gesonderte, bereits bereinigte Produktprüfbericht-Funktion. Dort startet „DEGIRO Goldhebelprodukte Probleme“ bei vorhandener Android-Unterstützung das Teilen-Menü statt ungefragt in die Zwischenablage zu schreiben.

## Sicherheit und Grenzen
- **Kein automatischer Versand.** `navigator.share` öffnet nur die Auswahl; Android/ChatGPT kann die Übernahme eines Textes verweigern oder abbrechen. Bob behauptet nie eine bestätigte ChatGPT-Zustellung.
- **Kein Token, Kennwort, Konto, Order, Broker-Fernzugriff, Rohlog, Bild oder Originalkurs im technischen Bericht.** Unvertrauenswürdige freie Issue-Titel/-Texte werden **nicht** in den technischen Bericht übernommen. Bei manuellen Issues stehen nur generische Kennzeichnung und Issue-Nummer.
- **Kopieren bleibt ein bewusst gewählter Rückfallweg**, nicht eine automatische Zusatzaktion.
- **Keine Hintergrundverbindung und kein neuer Android-Zugriff.** ChatGPT erhält erst nach deiner bewussten Auswahl und dem Absenden Inhalte; tatsächliche Analyse und sichere Code-Reparaturen erfolgen separat.
- Der Link `/handy/OPEN_PROBLEMS` ist ausschließlich eine Navigation in Bobs eigene authentifizierte Problemansicht. Er überträgt keine Diagnose über eine URL.

## Samsung-Abnahme nach veröffentlichtem, signiertem Android-Update
1. Neue `Bob-Handy.apk` als **Update** installieren, bestehende App nicht deinstallieren.
2. In ChatGPT `https://bob-private-scanner.onrender.com/handy/OPEN_PROBLEMS` antippen: „Bob – Handy“ öffnet kurz, danach Bob → Probleme.
3. Auf **„Fehlerdiagnose ohne Kopieren teilen“** tippen; im Android-Teilen-Menü **ChatGPT** auswählen; vor Absenden Inhalt prüfen. In ChatGPT selbst absenden.
4. Abbrechen: kein automatischer Versand. Ohne Unterstützung: Ersatztext und Kopierbutton in Bob → Probleme.
5. Produkt-Probleme mit dem separaten Button prüfen. Keine Echtgeldorder testen.

## Automatisierte Nachweise
- Node-Test `test_bob_diagnostic_chatgpt_handoff.js`: erlaubte Codes, Zahl/Zeit, geheimnisfreie Ausgabe, stale/unavailable, Native Share vs. Kopieren.
- `test_mobile_audit_share.js`: Produktdiagnose startet Native Share ohne implizites Kopieren.
- Kotlin-Tests der erlaubten HTTPS-Routen; CI/Android-Build, Security- und Live-Prüfung.
- Kein CI-Nachweis ersetzt den tatsächlichen Samsung-/ChatGPT-Übernahmetest.
