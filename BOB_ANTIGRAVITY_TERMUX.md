# Google Antigravity CLI auf Samsung / Termux – kostenloser Bob-Entwicklungsweg

**Status 09.11.2026:** Die alte Gemini CLI `@google/gemini-cli@0.67.0` wurde auf Android nur teilweise offline entpackt; die `--version`-Prüfung lief nach 7 bzw. 12 s ins Zeitlimit. Nach Googles offizieller Umstellung am **18.06.2026** werden persönliche Free-/Pro-/Ultra-Anfragen an diese alte CLI nicht mehr bedient. Ein weiterer Versuch mit deren Bundle ist für den Benutzer daher **nicht zielführend**.

## Warum Antigravity CLI statt der alten Gemini CLI?

- Google nennt für Antigravity CLI seit **02.10.2026 (v1.2.15)** **native Android-Termux-Binaries**, ohne proot-distro. Quelle: https://antigravity.google/docs/changelog?tab=cli
- Offizieller kostenloser Individual-Tarif: `$0/Monat` mit Nutzungslimits. Kein Paid-Upgrade und kein kostenpflichtiger Cloud-Server notwendig. Quelle: https://www.antigravity.google/pricing
- Die CLI wird als **`agy`** gestartet, nicht `gemini`. Unterstützt persönliche Google-Konten. **Die lokale Besitzeranmeldung ist erforderlich und darf nicht automatisiert oder durch einen API-Schlüssel aus GitHub ersetzt werden.** Quelle: https://antigravity.google/docs/install?tab=cli
- Die Antigravity-MCP-Konfiguration liegt in `~/.gemini/config/mcp_config.json` und nutzt `serverUrl`, **nicht** `httpUrl`. Quelle: https://antigravity.google/docs/mcp?tab=cli

## Bereits tatsächlich auf dem Samsung bestätigt

- Offizielle Termux-Paketquelle `https://packages.termux.dev/apt/termux-main` mit Erfolg getestet.
- Node v24.22.2 und npm v12.2.2 installiert. Für den nativen Antigravity-Binary-Weg ist die alte Gemini-npm-Installation nicht weiter nötig.
- Ein secretfreier Bob-MCP-Endpunkt `https://bob-private-scanner.onrender.com/mcp` liegt in der **alten** `~/.gemini/settings.json`, die Antigravity **nicht** als ihre globale MCP-Konfiguration verwendet. Keine bestehende lokale Datei überschreiben.
- Bob OAuth bietet aktuell einen zweiten, gesonderten Lesecallback `http://localhost:8765/oauth/callback` (PR #1505). **Noch kein separater Gemini/Antigravity-Grant nachgewiesen.**

## Sichere Installation nur in einer ausdrücklich geöffneten Handy-Wartungssitzung

1. Die offizielle Installer-Adresse ist `https://antigravity.google/cli/install.sh`. Sie wurde auf dem Samsung unter `~/.cache/bob-antigravity/install.sh` **nur heruntergeladen und in Auszügen geprüft, nicht ausgeführt**.
2. Das Skript erkennt `uname -o = Android` zusammen mit `aarch64` als Plattform `android_arm64`. Seine Veröffentlichungsquelle ist `https://antigravity-cli-auto-updater-974169037036.us-central1.run.app/manifests/android_arm64.json`.
3. Der Installer verlangt eine Manifest-SHA-512 für das heruntergeladene Paket und stoppt bei Fehlern. Weiterer Schritt: Veröffentlichungsgröße, Origin, Hash und Installationsziel prüfen; niemals `curl | bash` ungeprüft ausführen. Bei Unvereinbarkeit mit dem 20-Sekunden-Supervisor **nur** in legitimen, kurzen Einzelschritten installieren; keine detached/background-Tasks.
4. Ein späterer Test darf zunächst ausschließlich `agy --version` ausführen. **Keine Anmeldung, keine MCP-Verbindung, keine private Datenabfrage** während dieses technischen Tests.

## Private MCP-Verbindung: standardmäßig ausgeschaltet

Vorlage: `docs/antigravity-bob-readonly-mcp.disabled.json` im Repo. Sie enthält nur `serverUrl`, fünf klar benannte Bob-Lesetools und `disabled: true`. Kein Token, Client Secret, Google-API-Key oder privates Diagnosematerial. Antigravity unterstützt dieses Schema laut offizieller MCP-Dokumentation.

**Nicht ohne vorherige Prüfung aktivieren:** Googles Antigravity-OAuth verlangt einen zu Bob passend registrierten, exakt überprüften Callback. Die aktuelle Bob-Server-Registrierung akzeptiert nur die ChatGPT-URL bzw. den alten lokalen Gemini-CLI-Callback. Googles Antigravity-Dokumentation erwähnt für manuell konfigurierte OAuth-Clients dagegen `https://antigravity.google/oauth-callback`. Ob die **automatische dynamische Registrierung** diesen oder einen anderen Rückruf nutzt, muss erst anhand einer realen, freigegebenen Client-Anfrage überprüft werden. Keine Wildcard-, Redirect- oder Token-Weitergabe. Servercode nur nach sicherheitlich geprüftem PR und neuer Besitzerzustimmung erweitern.

**Schutz:** Während Google-Individual-Free aktiv ist, keine unbereinigten Bob-Privatdiagnosen, Depotwerte, Screenshots, Orders, Zugangsdaten oder vollständigen Protokolle an Antigravity senden. Vor jeglicher Privatnutzung über Google sind die dann geltenden Datenschutz-/Nutzungsbedingungen und der konkrete Datenumfang bewusst zu bestätigen. Freigaben bleiben einzeln widerrufbar; bestehender ChatGPT-Lesezugang bleibt unverändert.

## Was bereits funktioniert – ohne Antigravity

Die öffentliche GitHub-Actions-Gemini-Zweitprüfung und der Handy-gesteuerte Entwicklungsvorschlagsworkflow wurden mit echten Bot-Kommentaren nachgewiesen. Sie bleiben aktiv und kostenlos im vorgesehenen Kontingent, auch wenn diese lokale Antigravity-Verbindung noch nicht fertig ist.

**Akzeptanzkriterien:** `agy --version` erfolgreich auf Android → persönliche lokale Anmeldung erfolgreich → separater OAuth-Client korrekt registriert und vom Besitzer bestätigt → `bob_diagnostics` mit Zeitstempel lesbar → verbotene Termux-/Handy-/Push-/Order-Scopes nachweislich abgewiesen → Widerruf nur des Antigravity-Zugangs funktioniert. Vorher nie „private Anbindung abgeschlossen“ melden.
