# Bob Handy → Termux: begrenzte Verbindung

Die neue Brücke benutzt ausschließlich die offizielle Android
`com.termux.RUN_COMMAND`-Schnittstelle. Eine generische Fernkonsole,
SSH-Server, offene Ports, Shell-Skripte aus Chatnachrichten oder
Passwortübertragungen werden nicht eingerichtet.

## Vorbereitungen auf dem Samsung (einmalig)

1. Die **signierte Bob-Handy-Aktualisierung** aus dem bestehenden sicheren
   GitHub-Release installieren, nachdem Android-CI und Signaturprüfung grün
   sind. **Kein Debug-/Labor-APK** über die vorhandene App installieren.
2. Termux aus einer vertrauenswürdigen Quelle öffnen. Die Termux-App und
   eventuell zusätzlich installierte Termux-Plugins dürfen nicht zwischen
   inkompatiblen Signaturquellen gemischt werden.
3. In Termux diese normalen Paketbefehle ausführen:

   ```sh
   pkg update -y
   pkg install -y python python-cryptography curl
   mkdir -p "$HOME/bob-sicher" "$HOME/.termux"
   curl --fail --silent --show-error --location \
     'https://raw.githubusercontent.com/ichrob/gold-dashboard1/71d9dfdf9cf14d6dcc041e472bedebd164b4a145/bob_offline_key_escrow.py' \
     --output "$HOME/bob-sicher/bob_offline_key_escrow.py"
   chmod 600 "$HOME/bob-sicher/bob_offline_key_escrow.py"
   python "$HOME/bob-sicher/bob_offline_key_escrow.py" --help
   ```

   Dieser öffentliche, versionsfest adressierte Quellcode enthält keine
   geheimen Schlüssel. Bei fehlgeschlagenem Download oder Prüfung abbrechen.

4. Die Android-Termux-Kopplung bewusst freigeben. In
   `~/.termux/termux.properties` genau eine aktive Zeile
   `allow-external-apps = true` eintragen (andere Einstellungen beibehalten).
   Danach `termux-reload-settings` aufrufen. Diese zusätzliche Freigabe
   gestattet **nur Apps mit der separat erteilten Android-Permission**
   `com.termux.permission.RUN_COMMAND` die Termux-Auftragsschnittstelle.
   Sie bleibt ein weitreichendes Android-Recht und sollte nur für die
   vertrauenswürdige Bob-Handy-App freigegeben werden.
5. Android → Einstellungen → Apps → **Bob Handy** → Berechtigungen →
   Zusätzliche Berechtigungen → **Termux-Befehle ausführen** erlauben
   (genaue Bezeichnungen können je Android-Version abweichen).

## Abnahme in Bob Handy

- Auf `Termux-Verbindung prüfen` tippen. Bob startet ausschließlich
  `python ~/bob-sicher/bob_offline_key_escrow.py --help` im Termux-Hintergrund.
  Der sehr kurze Hilfebefehl erzeugt normalerweise keine dauerhaft sichtbare
  Termux-Sitzung.
- Die offizielle Termux-Rückgabe wird durch einen einmaligen, nicht exportierten
  Android-Empfänger ausgewertet. Bob Handy liest **nur** die beiden festen
  Statuszahlen (Termux-internes Ergebnis und Exitcode). Es liest weder stdout
  noch stderr, Umgebungsvariablen, Token, Dateiinhalte oder Termux-Sitzungen.
- Erst `TERMUX_CHECK_EXECUTED` mit Termux-Status OK und Exitcode 0 gilt als
  Ausführungsbeleg des festen Python-Hilfetests. `TERMUX_REQUESTED` bedeutet
  weiterhin nur, dass Android den Startauftrag angenommen hat.
- Bei Fehler, ausbleibender Quittung, fehlender Android-Freigabe oder Termux
  wird ein fester Fehler- oder Unbestätigt-Status angezeigt. Der Test darf
  jederzeit erneut lokal angestoßen werden.
- Wenn der private Bob-Handy-Lesedienst verbunden ist und du selbst eine
  **15-Minuten-Handysitzung** gestartet hast, darf ChatGPT über den bestehenden
  kontrollierten Phone-Befehl `termux_check` einmalig denselben fest eingebauten
  `--help`-Test anfordern. Keine Parameter, Shell-Eingaben, Befehlsfolgen,
  Gerätekonten oder Secrets können übergeben werden. Ein angenommenes Intent
  ist wiederum **keine** bestätigte Ausführung.

## Tatsächliche Offline-Schlüsselsicherung ohne Kopierbefehle

Die von CI geprüften Python-Skripte `bob_offline_key_escrow.py` und
`bob_render_to_offline_escrow.py` sind als unveränderliche Assets in der
offiziell signierten Bob-Handy-APK enthalten. Der Android-Build verweigert
die Freigabe, falls sie von den geprüften GitHub-Originalen abweichen.

Nur die **lokale** Schaltfläche **Archivschlüssel offline sichern – nur lokal**
öffnet nach einer zweiten Bestätigung Termux im Vordergrund. Ein fester
Python-Bootstrap überträgt die zwei *nicht geheimen*, komprimierten
APK-Assets und kontrolliert ihre SHA-256-Prüfsummen. Bereits vorhandene,
abweichende lokale Skripte werden aus Sicherheitsgründen **nicht**
überschrieben. Das Programm startet dann direkt die sichere Render-Variante.

Dort werden ausschließlich lokal, verdeckt und ausdrücklich vom Gerätebesitzer
eingegeben:

1. Ein kurzfristig berechtigter Render-API-Schlüssel, um direkt den **alten
   Originalwert** von `PUSH_SERVICE_TOKEN` auf `bob-push-service` per HTTPS
   abzurufen. Die verbundene ChatGPT-Render-App kann den geheimen Wert
   selbst nicht auslesen. Ein uneingeschränkter API-Schlüssel ist risikoreich;
   ihn nach dem Vorgang sofort widerrufen.
2. Ein **separates, langes Offline-Backup-Passwort**, zweimal zur Bestätigung.

Kein geheimer Parameter und keine Eingabe gelangt über Bob Handy, ChatGPT,
GitHub oder die Fernsteuerung. Es wird ausschließlich eine lokale AES-GCM-Datei
`~/bob-sicher/bob-archive-root.vault` mit restriktiven Rechten erzeugt und
**nur lokal** wieder geöffnet und auf Gleichheit mit dem ursprünglichen
Schlüssel geprüft. Das ist noch **keine unabhängige USB-Sicherung**.

Anschließend muss der Gerätebesitzer diese verschlüsselte Datei über ein
vertrauenswürdiges Android-Dateiprogramm auf einen USB-Stick kopieren. Eine
erneute Prüfung *von der USB-Kopie* gegen das passende verschlüsselte
Google-Drive-Archiv und dessen Quittungsbeleg bleibt erforderlich, bevor
`recoveryKeyVerified` als wahr gelten darf. Dafür gibt es keine heimliche
Fernbedienung oder automatische Löschfreigabe.

Bob setzt **keinesfalls** `recoveryKeyVerified=true` und startet keinen
Referenz-Piloten nur weil eine Brückensitzung oder ein lokales Skript gestartet
wurde. Kein SSH-Server, kein unbeaufsichtigtes Termux-Programm, keine
Veränderung an DEGIRO, Marktanalysen oder Echtgeldorders.

## Termux öffnet sich nicht automatisch auf Android 10+

Das lokale Backup in Bob Handy überträgt zunächst einen festen
`RUN_COMMAND`-Auftrag an Termux. Android kann dessen Terminal-Sitzung erstellen,
ohne die Termux-Oberfläche sofort in den Vordergrund zu holen. Deshalb
versucht Bob Handy nun **nach der bewusst bestätigten lokalen
Backup-Aktion** zusätzlich, ausschließlich die installierte
`com.termux`-App über den offiziellen Launcher zu öffnen.

Das Öffnen der App beweist noch **keine** erfolgreiche Ausführung und keine
gesicherte Root. Es werden keine Geheimnisse als Intent-Extras übergeben.
Diese Aktivierung geschieht **nie** durch ChatGPT-Fernaktionen und verändert
den isolierten Hintergrund-Verbindungstest nicht.

Falls Android/Samsung den automatischen Vordergrundwechsel weiterhin
blockiert, muss Termux am Gerät manuell geöffnet und die neueste Sitzung
gewählt werden. Die offizielle Termux-Dokumentation beschreibt dafür auf
Android 10+ optional die Android-Sonderberechtigung „Über anderen Apps
einblenden“ für Termux. Diese Berechtigung ist weitreichend und soll nur
auf dem vertrauenswürdigen eigenen Gerät bewusst freigegeben werden.
Die App erzwingt sie nicht und schaltet sie nicht selbst ein.

## Sicherheitsgrenzen

- `RUN_COMMAND` ist ein weitreichendes Android-Recht. Bob Handy nutzt es
  ausschließlich mit dem **fest programmierten Python-Pfad** und dem
  festgelegten Verbindungstest bzw. dem lokal freigegebenen, aus signierten
  APK-Assets geprüften Offline-Start. Es gibt keine freien Befehlsparameter.
- Remote ist ausschließlich `termux_check` möglich; `LOCAL_ESCROW` ist
  nur über den bewusst bestätigten lokalen App-Dialog erreichbar.
- Beim Hilfetest kann ausschließlich ein fester Exitcode über den
  nicht exportierten Android-Empfänger an Bob Handy zurückgegeben werden.
  Bei der geheimen Offline-Sicherung ist überhaupt kein Ergebnisempfänger
  registriert. Es werden weder Termux-Umgebungsvariablen noch Eingabe-,
  stdout- oder stderr-Inhalte an ChatGPT/Bob übertragen.
- Das Stoppen/Sperren der Handysitzung bleibt erhalten. Alte OAuth-Tokens
  erhalten keine neuen Remote-Steuerrechte.
- Ein fehlender physischer Gerätetest wird niemals als erfolgreiche Kopplung
  markiert.
