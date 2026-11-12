# Bob: direkte lokale Render-Sicherung nach Termux (kein Schlüssel im Chat)

**Status:** vorbereiteter, lokaler Bedienablauf. Er funktioniert erst, wenn die
Eigentümerin/der Eigentümer einen gültigen Render-API-Schlüssel **privat am
Samsung** eingibt. Der Verbindungsstatus Bob Handy ↔ Termux und ein grüner
GitHub-Test sind KEIN Nachweis, dass der Archivschlüssel bereits gesichert ist.

## Warum dieser Weg

Die bislang bestätigte verschlüsselte Gesamtsicherung leitet ihren AES-Schlüssel
aus dem damaligen `PUSH_SERVICE_TOKEN` von `bob-push-service` ab. Der
verbundene Render-MCP-Zugriff kann bestehende geheimen Umgebungswerte nicht
lesen. Render dokumentiert dagegen die direkte HTTPS-Abfrage
`GET /v1/services/{serviceId}/env-vars/{envVarKey}` (nur Variablen
direkt auf einem Dienst, **nicht** aus verknüpften Environment Groups).

Dieses kleine lokale Tool verbindet sich unter der fest programmierten URL
`https://api.render.com`, findet ausschließlich `bob-push-service`, liest
ausschließlich `PUSH_SERVICE_TOKEN` und schreibt sofort eine AES-GCM-
verschlüsselte Tresordatei in den privaten Termux-Ordner. Keine Kopie
des Originalschlüssels in GitHub, ChatGPT, Render-Logs, Android-Zwischenablage,
CLI-Argumenten oder eine unverschlüsselte Datei.

## Vor dem Start

- Die vorhandene `bob_offline_key_escrow.py` muss unter
  `~/bob-sicher/bob_offline_key_escrow.py` installiert sein, ebenso Python
  und `python-cryptography` (bereits lokal geprüft).
- Die neue Datei `bob_render_to_offline_escrow.py` ebenfalls **direkt auf
  dem Samsung** nach `~/bob-sicher/` laden und im Terminal manuell prüfen.
  Eine konkrete Commit-ID zum Pinnen erst nach geprüfter Veröffentlichung
  aus der Main-Historie übernehmen.
- Ein **eigens für diesen einmaligen Vorgang** erstellter Render-API-Schlüssel
  wird benötigt. Wenn im Render-Account bereits Scopes zur Verfügung stehen,
  die Leserechte für den betroffenen Dienst/Umgebungswert erlauben, nur diese
  auswählen. Scoped API keys sind bei Render zum Zeitpunkt 03.11.2026
  nicht allgemein freigegeben. Eine nicht eingeschränkte API-Key-Credential
  hat weitgehende Render-Rechte: vor der Erstellung das Risiko bewusst
  akzeptieren und **nach erfolgreicher Prüfung sofort widerrufen**.
- Den API-Schlüssel niemals im Chat oder einer Issue-Nachricht teilen.
  Das Programm fordert ihn nur über eine verdeckte Eingabe in Termux an.

## Einmaliger lokaler Ablauf

```bash
python "$HOME/bob-sicher/bob_render_to_offline_escrow.py"
```

1. Den temporären Render-API-Schlüssel im lokalen versteckten Prompt
   eingeben, nicht als Bash-Befehl oder Parameter.
2. Das Skript liest und akzeptiert ausschließlich die vorher festgelegte
   Render-Variable. Liegt sie in einer Environment Group oder ist sie
   nicht mehr verfügbar, verweigert es die Aktion, ohne einen Ersatzschlüssel
   zu erfinden oder irgendetwas auf Render zu verändern.
3. Ein **anderes**, langes Offline-Passwort zweimal verdeckt eingeben,
   getrennt vom API-Schlüssel und von bestehenden Dienstgeheimnissen.
4. Es entsteht
   `~/bob-sicher/bob-archive-root.vault` (ausschließlich verschlüsseltes
   AES-256-GCM, exklusiv mit `0600` angelegt). Bei einem Fehler wird keine
   unverschlüsselte Datei geschrieben; ein vorhandener Tresor wird niemals
   überschrieben.
5. Das Programm liest die lokale Kopie unmittelbar testweise zurück und
   vergleicht die Daten mit dem ursprünglichen Render-Wert **nur im
   Arbeitsspeicher**. Das Ergebnis lautet
   `localRoundtripVerified=true`. Das ist **noch kein** unabhängiger
   Wiederherstellungsbeleg.

## USB und Test des alten Archivs

- Die fertige *.vault-Datei über Android **Eigene Dateien** / einen
  vertrauenswürdigen Dateimanager auf den USB-Stick übertragen. Gegebenenfalls
  nur die verschlüsselte Datei mittels Android-Dateifreigabe aus dem
  privaten Termux-Ordner exportieren. Kein Klartext, keine Zugangstokens.
- Die Kopie vom USB-Stick erneut in einem isolierten Verzeichnis importieren,
  entschlüsseln und prüfen, bevor sie als dauerhaft nutzbar gilt. Ein zweites
  unabhängiges Medium ist empfehlenswert. Backup-Passwort getrennt verwahren.
- Das alte, authentifizierte Original-Archiv
  `bob-evidence-*.zip.aesgcm` **und die zugehörige**
  `*-verified.json` vom privaten Google-Drive-Ordner heruntergeladen mit
  `bob_offline_key_escrow.py verify` gegen das Wiederherstellungspasswort
  prüfen. Erst das beweist, dass der auf USB gesicherte Root wirklich das
  frühere Archiv entschlüsseln kann.
- Die bereits geprüfte Wiederherstellung auf einer getrennten PostgreSQL-
  Instanz ist ein separater Beleg. Für ein vollständiges Disaster-Recovery-
  Urteil muss der alte USB-Root auf einem vom produktiven Render unabhängigen
  Gerät gegen genau dieses Archiv geprüft sein. Kein Original-DELETE oder
  Verweismigrations-Pilot, solange dieser Nachweis fehlt.

## Grenzen und Fehlerfälle

- Nur GET an `api.render.com`; Redirects sind deaktiviert, der Antwort-
  umfang begrenzt, Zielname und Variablenname fest im Code, keine freien
  Parameter. Kein neues Bob-HTTP-Endpoint, kein Server-Secret-Export.
- Nicht auf einer per ChatGPT fernsteuerbaren offenen Termux-Konsole
  ausführen. Der lokale versteckte Prompt ist hierfür erforderlich.
- Gibt Render 401/403/404, eine uneindeutige Dienstliste oder eine nicht
  direkt am Dienst gesetzte Variable zurück, bricht die lokale Sicherung
  ab. Keine automatische Rotation, kein Zurücksetzen, keine Live-Mutation.
- Die Verwendung eines temporären Render-API-Schlüssels stellt ein
  zusätzliches Sicherheitsrisiko dar; wenn der Nutzer dies nicht möchte,
  stattdessen das Originalgeheimnis in der authentifizierten Render-Umgebung
  selbst lokal (ohne Chat-Übertragung) in das bereits vorhandene Offline-
  Sicherungstool eingeben. Keine API-Zugangsdaten übermitteln.

## Korrektur vom 03.11.2026: Einzelwertantwort und sichere Fehlerdiagnose

Die offizielle Render-OpenAPI unterscheidet zwei Antwortformen:
- `GET /v1/services/{id}/env-vars` (Liste): `[{ "envVar": { "key": "...", "value": "..." }, "cursor": "..." }]`
- `GET /v1/services/{id}/env-vars/PUSH_SERVICE_TOKEN` (Einzelwert):
  **direkt** `{ "key": "PUSH_SERVICE_TOKEN", "value": "..." }`.

Die erste Version des lokalen Programms prüfte irrtümlich auch beim
Einzelwert auf die Listenhülle `envVar` und brach daher mit
`TransportBlocked` ab, sogar wenn Render 200 zurückgegeben hatte.
Die korrigierte Version akzeptiert **ausschließlich** die direkte,
offiziell dokumentierte Einzelwertform.

Außerdem meldet sie jetzt nur fest definierte, gefahrlos teilbare
Diagnosecodes:
- `RENDER_AUTH_REJECTED`: HTTP 401, API-Schlüssel ungültig/abgelaufen
- `RENDER_ACCESS_DENIED`: HTTP 403, benötigter Zugriff fehlt
- `RENDER_RESOURCE_NOT_FOUND`: HTTP 404, Dienst/Variable nicht gefunden
  (eine verknüpfte Environment Group wird nicht als Dienstvariable gelesen)
- `RENDER_RATE_LIMITED`: HTTP 429
- `RENDER_API_UNREACHABLE`: Netzwerk/TLS/JSON-Antwort unbrauchbar
- `ENV_VAR_UNAVAILABLE_OR_LINKED_GROUP`: Einzelwert nicht direkt vorhanden
- `LOCAL_OR_SCHEMA_BLOCKED`: lokale Vorbedingung oder unerwartete
  Antwortform ohne weitere sensible Details.

Die Ausgabe enthält weiterhin **keinen** Render-Zugangsschlüssel,
Originalwert, Hostnamen, URL, Response Body oder Umgebungsvariablen.
Das genaue Problem aus einem alten `TransportBlocked`-Screenshot
ist nicht eindeutig ableitbar. Ein erfolgreicher Code-Fix beweist auch
keine erfolgreiche USB-Kopie oder Archiv-Wiederherstellung.

Auf Samsung wird die korrigierte Python-Datei bei einem lokal
bestätigten Start nur dann automatisch aktualisiert, wenn die vorhandene
Datei exakt dem bislang signierten App-Code entspricht. Abweichende
Programme und bestehende `.vault`-Dateien werden nicht überschrieben.
Ein erneut gestarteter Sicherungslauf erfordert weiterhin die
ausdrückliche lokale Bestätigung, einen gültigen privaten Render-API-Key
und das getrennte Backup-Passwort. API-Key nach der Sicherung widerrufen.

## Korrektur: TypeError nach zweiter Backup-Passworteingabe

Beim Samsung-Gerät meldete Termux am 03.11.2026 nach `Repeat passphrase
(hidden):` den festen Code `LOCAL_OR_SCHEMA_BLOCKED` und `TypeError`.

Die alte Python-Funktion verglich zwei Strings mit
`hmac.compare_digest(password, repeat)`. `compare_digest` akzeptiert
Unicode-Strings nur dann, wenn sie ausschließlich ASCII-Zeichen enthalten:
bereits ein gleiches Passwort mit `ä`, `Ö` oder einem Emoji löst
`TypeError` aus. Das passt zum Zeitpunkt des Abbruchs, beweist jedoch
nicht, welche Zeichen der Nutzer tatsächlich verwendet hat.

Die bestätigte Korrektur vergleicht stattdessen die **UTF-8-codierten
Bytes** beider Eingaben. Das entspricht genau der bereits von
`hashlib.scrypt` verwendeten Codierung. Dadurch bleibt das AES-GCM-
Tresorformat `bob-offline-root-escrow-v1` unverändert und es gibt keine
Passwort-Normalisierung, Kürzung oder stille Änderung der Schlüsselableitung.
Abweichende Eingaben werden weiterhin abgelehnt.

Synthetische Tests verwenden Umlaute und Emoji sowohl für das lokale
Render-Skript als auch für das separat ausführbare Verschlüsselungstool.
**Kein echtes Passwort wird protokolliert, übertragen oder für Tests benötigt.**

Nach diesem Fehler muss vor dem nächsten Versuch geprüft werden, ob
`~/bob-sicher/bob-archive-root.vault` bereits existiert; **niemals
überschreiben**. Das Skript verweigert vorhandene Tresordateien bereits
vor jeder neuen API-Abfrage. Bei der vermuteten Unicode-Ursache endet
die Ausführung vor dem Schreiben; ein tatsächlicher Dateistand wurde
am Gerät noch nicht unabhängig bestätigt.

Die neue signierte APK darf ausschließlich die exakt bekannten früheren
signierten Python-Programmdateien aktualisieren. Sie verändert keine
vorhandene `.vault`-Datei und erweitert keine Fernsteuerrechte.

## Weitere Diagnose 03.11.2026 – TypeError trotz UTF-8-Fix

Auf Samsung v10496 trat `LOCAL_OR_SCHEMA_BLOCKED` mit `TypeError`
erneut **nach** der Passwortbestätigung auf. Damit ist die ursprüngliche
Nicht-ASCII-`compare_digest`-Vermutung allein nicht ausreichend;
die genaue Fehlerstelle wurde nicht aus dem redigierten Screenshot
ersichtlich. Keine echten Passwörter und Schlüssel wurden eingesehen.

Neuer sicherer Diagnoseweg:

- Bei jedem lokalen Backup-Start wird **vor jeglicher Eingabe** ein
  flüchtiger AES-256-GCM/Scrypt-Schreib-/Lese-Test mit ausschließlich
  synthetischen Daten durchgeführt. Die kurzlebige Testdatei liegt
  isoliert im Termux-Temporärverzeichnis und wird automatisch entfernt.
  Ein fehlgeschlagener Test beendet den Ablauf **vor** dem Render-API-
  Schlüsselprompt. Es wird kein produktiver Root gelesen.
- Der Verschlüsselungshelfer klassifiziert Fehler mit unveränderlichen
  Phasencodes `LOCAL_KDF_FAILED`, `LOCAL_ENCRYPT_FAILED`,
  `LOCAL_WRITE_FAILED`, `LOCAL_DECRYPT_FAILED`,
  `LOCAL_ROUNDTRIP_FAILED`; gespeichert wird ausschließlich
  die Fehlerklasse (z.B. `TypeError`), **niemals** die Ausnahme-
  Nachricht, die Eingabe oder ein Stacktrace.
- Die Ausgabe enthält den ungefährlichen, festen Versionsbeleg
  `programRevision=termux-local-crypto-selftest-1`, sodass künftig
  erkennbar ist, ob die neue Software auf Termux ausgeführt wurde.
- Nur die unveränderten, exakt bekannten signierten Vorgängerdateien
  dürfen durch die neue signierte Bob-Handy-App automatisch aktualisiert
  werden. Bereits angelegte `.vault`-Dateien und abweichende
  benutzerdefinierte Skripte bleiben unberührt.
- Ein neuer API-Schlüssel oder ein anderes Backup-Passwort ist **keine
  geeignete Maßnahme** gegen diesen lokalen `TypeError`. Es darf
  keine blinde Wiederholung oder eine unverschlüsselte Sicherung geben.

Erfolg wird weiterhin ausschließlich bei `escrow-ciphertext-created`
und `localRoundtripVerified=true` akzeptiert. Ein bestandener
synthetischer Test ist noch **keine** unabhängige USB-Sicherung und
keine Freigabe zum Löschen von Originaldaten.
