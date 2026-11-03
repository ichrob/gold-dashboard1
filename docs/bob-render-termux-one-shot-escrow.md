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
