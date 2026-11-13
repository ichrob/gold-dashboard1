# Gemini CLI auf Termux: unabhängiger Offline-Starttest

**Ziel:** Das bereits auf dem Samsung heruntergeladene, offizielle Archiv
`~/.cache/bob-gemini-cli/google-gemini-cli-0.67.0.tgz` ohne neue Downloads,
Google-Anmeldung, private Bob-Daten oder Änderungen an den bestehenden Gemini-
Einstellungen auf technische Startfähigkeit prüfen.

## Geprüfter Ausgangsstand (09.11.2026)

Die vorherige Bob-Handy-Wartung hat die offizielle Termux-Paketquelle erfolgreich
eingestellt und `nodejs-lts 24.22.2`, `npm 12.2.2` installiert.
Das offizielle `@google/gemini-cli@0.67.0`-Paket (rund 20 MB, aus npm)
wurde gecacht. Die isolierte `npm install --offline` wurde nach 15 Sekunden
abgebrochen (`INSTALL_EXIT=124`); dies **beweist keine Installation**.
Das Paket enthält nach lokalem Test `package/bundle/gemini.js`.

## Separat kontrollierbare Offline-Schritte

`gemini_termux_offline_probe.py` ist ein standardbibliotheksbasiertes,
geprüftes Hilfsprogramm. Es besitzt ausschließlich drei feste Aktionen:

1. `inspect`: Name/Version/Dateityp und Größen des vorhandenen Originalarchivs
   prüfen; kein Entpacken.
2. `extract`: **nur** `package/bundle/gemini.js` in ein separates
   `~/.cache/bob-gemini-cli/isolated-probe/` kopieren. Keine Tar-`extractall`-
   Verwendung, keine Überschreibung bestehender Dateien.
3. `version`: `node .../gemini.js --version` mit einer neuen, leeren
   temporären `HOME`-Konfiguration, ohne Google-/Bob-Tokens und mit
   **sieben Sekunden Prozess-Timeout** ausführen.

Für das begrenzte Termux-Wartungswerkzeug müssen dies **drei getrennte Aufträge**
sein; die gesamte ferngesteuerte Ausführung bleibt auf 20 Sekunden je Auftrag
begrenzt. **Kein Hintergrundprozess**, keine Freigabeumgehung, keine
Berechtigungserweiterung.

Der Code kann erst dann aufs Handy übertragen werden, wenn eine frische,
ausdrücklich freigegebene Bob-Handy-Sitzung besteht und der Übertragungsweg
legitim ist. Aus einem grünen GitHub-CI-Lauf allein folgt keine echte
Android-Kompatibilität. Kein Download von unbekannten Community-Forks.

## Grenzen und Schutz

Die normale Gemini-Handy-App erhält durch diesen Test keine privaten MCP-Rechte.
Android/Termux ist **keine offiziell unterstützte Gemini-CLI-Plattform**;
auch `--version` ist noch kein Beleg eines funktionierenden interaktiven
OAuth-Callbacks. Googles Gemini CLI verlangt einen echten Browser und einen
Empfänger für `http://localhost:8765/oauth/callback`. Für eine spätere private
Bob-Anbindung ist deshalb eine neue persönliche OAuth-Freigabe erforderlich.

Das kostenlose Google-Modell darf bis zu einer gesonderten Datenschutzfreigabe
keine privaten Bob-Diagnosen, Depotdaten oder Screenshot-Originale bekommen.
Keine Gemini-/GitHub-/ChatGPT-API-Schlüssel im Termux-Skript eintragen.

**Tatsächlicher Android-Livetest vom 09.11.2026:** `inspect` war erfolgreich.
Die erste Extraktion scheiterte an fehlendem `os.link()` in Termux-Python 3.14.
Der geprüfte Portabilitätsfix nutzt daher ausschließlich `open("xb")` und
verhindert weiterhin das Überschreiben vorhandener Dateien. Damit wurde
`EXTRACTED_OFFLINE_NO_SECRETS` bestätigt. Die einzelne Startdatei ist jedoch
**nicht ausführbar ohne weitere Chunk-Dateien**. Das npm-Archiv enthält 446
Bundle-Dateien. Eine getrennte, lokal beschränkte Archivprüfung (449 Mitglieder,
nur normale Dateien/Verzeichnisse, keine Traversalpfade, 94,4 MB) wurde
erfolgreich ausgeführt; das vollständige Bundle wurde daraufhin in einem
separaten Verzeichnis mit Python-`tarfile` und `filter="data"` entpackt.
Selbst damit endeten auf dem Android-Gerät die reinen Versionsstarts mit
**`VERSION_TIMEOUT` bei sieben und zwölf Sekunden**. Deshalb ist weiterhin
**kein funktionierender Gemini-CLI-Client nachgewiesen**. Keine weiteren
Startversuche oder privaten OAuth-Freigaben ohne neues überprüfbares Vorgehen.

`extract` in diesem Prüfskript bleibt **nur eine sichere Einzeldatei-/
Manifestprüfung**, keine vollständige Gemini-Installation. Eine erfolgreiche
Versionsprüfung müsste die gesamte, gesondert validierte Bundle-Struktur
verwenden; ein isoliertes Einzeldatei-Ergebnis darf nie als funktionsfähige CLI
ausgegeben werden.
