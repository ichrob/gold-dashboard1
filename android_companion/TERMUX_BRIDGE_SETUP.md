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

- Auf `Termux-Verbindung prüfen` tippen. Bob öffnet nur
  `python ~/bob-sicher/bob_offline_key_escrow.py --help`.
- Falls diese Berechtigung oder Termux fehlt, meldet Bob einen festen
  Fehlercode, niemals Dateiinhalte oder einen Schlüssel.
- Bei `TERMUX_REQUESTED` hat Android lediglich den Startauftrag angenommen;
  das ist ausdrücklich **kein** Beweis, dass das Python-Skript erfolgreich lief.
  Das echte Ergebnis muss auf dem Termux-Bildschirm geprüft werden.
- Wenn der private Bob-Handy-Lesedienst verbunden ist und du selbst eine
  **15-Minuten-Handysitzung** gestartet hast, darf ChatGPT über den bestehenden
  kontrollierten Phone-Befehl `termux_check` einmalig denselben fest eingebauten
  `--help`-Test anfordern. Keine Parameter, Shell-Eingaben, Befehlsfolgen,
  Gerätekonten oder Secrets können übergeben werden. Ein angenommenes Intent
  ist wiederum **keine** bestätigte Ausführung.

## Tatsächliche Offline-Schlüsselsicherung

Nur die lokale Schaltfläche **Archivschlüssel offline sichern – nur lokal**
öffnet nach einer zweiten expliziten Bestätigung das geprüfte Python-Skript
im Vordergrund von Termux. Der Originalschlüssel und das **separate**
Backup-Passwort werden dort verdeckt eingegeben. Kein geheimer Parameter
gelangt über Bob Handy, ChatGPT, GitHub oder HTTP.

Du musst den exakt ursprünglichen Schlüssel aus dem **autorisierten privaten
Render-Geheimnisspeicher** auf einem sicheren lokalen Weg haben. Wenn dessen
Wert nicht mehr lesbar ist, **nicht rotieren, ersetzen oder raten**. Der
Sicherungsdialog hilft in diesem Fall nicht weiter.

Der verschlüsselte Beleg wird lokal als
`~/bob-sicher/bob-archive-root.vault` erstellt. Das ist noch **keine
USB-Sicherung**. Du musst die Datei über eine vertrauenswürdige Dateiverwaltung
auf den eigenen USB-Stick kopieren, eine zweite Kopie extern aufbewahren und
die Wiederherstellung auf einem unabhängigen Gerät tatsächlich testen.
Passwort getrennt aufbewahren.

Bob setzt **keinesfalls** `recoveryKeyVerified=true` und startet keinen
Referenz-Piloten nur weil eine Brückensitzung oder ein lokales Skript gestartet
wurde. Kein SSH-Server, kein unbeaufsichtigtes Termux-Programm, keine
Veränderung an DEGIRO, Marktanalysen oder Echtgeldorders.

## Sicherheitsgrenzen

- `RUN_COMMAND` ist ein weitreichendes Android-Recht. Bob Handy nutzt es
  ausschließlich mit dem **fest programmierten Python-Pfad** und den beiden
  festgelegten Befehlsvarianten. Das Dateiziel ist ebenfalls fest.
- Remote ist ausschließlich `termux_check` möglich; `LOCAL_ESCROW` ist
  nur über den bewusst bestätigten lokalen App-Dialog erreichbar.
- Es werden weder Termux-Umgebungsvariablen noch Eingabe-, stdout- oder
  stderr-Inhalte an ChatGPT/Bob übertragen.
- Das Stoppen/Sperren der Handysitzung bleibt erhalten. Alte OAuth-Tokens
  erhalten keine neuen Remote-Steuerrechte.
- Ein fehlender physischer Gerätetest wird niemals als erfolgreiche Kopplung
  markiert.
