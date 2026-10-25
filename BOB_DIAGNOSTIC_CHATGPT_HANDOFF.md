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


## Rückweg ChatGPT → Bob: Fall-ID, Code-Nachweis und unabhängige Erholung

**Stabile Fall-ID:** `BOB-<GitHub-Issue-Nummer>-<bekannter-Fehlercode>` erscheint
in Bobs Problemansicht sowie im technischen Diagnosebericht. Derselbe Fehlercode
ist nicht dasselbe wie dieselbe Issue-Nummer, wenn ein späterer Rückfall neu
erfasst wird.

**Nachweis einer Code-Änderung (nur Repository-Schreibberechtigte):** Nach
einem konkreten ChatGPT-Prüfauftrag kann der berechtigte Assistent eine
bestehende GitHub-Issue im Repository `ichrob/gold-dashboard1` lesen und im
Issue-**Body** den vorhandenen Inhalt erhalten und folgende exakt formatierte
Markierungen ergänzen. Dazu muss es bereits einen **wirklichen** PR und
Commit geben:

```
<!-- BOB_KI_STATUS:testing -->
<!-- BOB_KI_REVIEW:pr=123;sha=0123456789abcdef0123456789abcdef01234567;phase=ci-tested -->
```

Erlaubte `phase`-Werte: `proposed`, `ci-tested`,
`deployed-unverified`. Die Markierung ist lediglich ein
**Code-/PR-Prüfverweis**. Sie berechtigt keine Order, ändert keine Produktdaten
und kann auch nach grüner CI **keine bestätigte Reparatur** behaupten.
Nur Markierungen von `ichrob` oder `github-actions[bot]` an einer
erlaubten Issue werden für Bobs Statusansicht übernommen. Beliebige
Issues, fremde URLs und freie Kommentartexte werden nicht übernommen.

**Technisch nachgeprüfte Erholung:** Der bestehende GitHub-Watchdog
kontrolliert die anonymen technischen Gesundheitscodes. Bevor er ein
technisches Problem automatisch schließen und als erholt melden darf,
muss die Fehlerart in **zwei im Abstand von 15 Sekunden neu gestarteten
Prüfungen** fehlen. Er schreibt dann eine fest definierte, datensparsame
Erholungsbeobachtung (Issue-Nummer, Fehlercode, UTC-Zeit, fester Nachweistyp)
in die bestehende `bob-status/problem-index.json`-Spiegeldatei.
Bob zeigt bis zu 20 Beobachtungen aus den letzten 30 Tagen unter
**„Technisch nachgeprüfte Erholungen“**; erneute offene Probleme derselben
Fehlerart verdecken frühere Erholungen. Eine technische Erholung beweist
**nicht**, dass der ChatGPT-Code-Fix die Ursache war.

**Strikte Ausnahme:** Produktnachweis-, KO-, Hebel-, Screenshot-,
Trade-Einrichtungsprobleme werden nicht allein durch fehlende
Gesundheitscodes geschlossen oder als technisch bestätigt dargestellt.
Dafür ist weiterhin eine eigenständige, geprüfte Originalquelle nötig.

**Wichtig:** Ein neues ChatGPT-Gespräch wird durch Android-Teilen separat
eröffnet und nicht mit diesem Gespräch synchronisiert. Das GitHub-Issue
ist der nachvollziehbare Übergabepunkt **nur wenn** ChatGPT tatsächlich
die berechtigten GitHub-Werkzeuge verwendet und das Ergebnis nach Prüfung
dort protokolliert. Es gibt keinen automatischen Zugriff auf fremde
Chatverläufe und keine unbeaufsichtigte ChatGPT-Hintergrundausführung.
