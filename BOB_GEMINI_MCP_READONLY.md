# Gemini CLI: eigener, sicherer Lesezugriff auf Bob (MCP)

**Status:** Dies ist zunächst eine geprüfte Codevorbereitung, **keine** automatisch eingerichtete Verbindung in der Gemini-Handy-App. Erst nach CI, Merge, tatsächlichem Deployment beider Bob-Dienste, Besitzer-Anmeldung/Freigabe und erfolgreichem OAuth-Live-Test darf der Zugang als funktionsfähig gelten.

## Warum ein zweiter OAuth-Client?
Bobs bisherige private OAuth-Verbindung verwendet den exakten ChatGPT-Callback `https://chatgpt.com/connector_platform_oauth_redirect`. Diese Verbindung und sämtliche vorhandenen Berechtigungen bleiben unverändert. Die neue Ergänzung akzeptiert einen **zweiten separaten** öffentlichen Client, ausschließlich mit Callback `http://localhost:8765/oauth/callback`, wenn dort lokal ein autorisierter Gemini-CLI-Prozess den OAuth-Rückruf annimmt. Dynamische Registrierung darf keine abweichenden Callback-Hosts, Ports, Pfade oder Query-Parameter verwenden.

Google Gemini CLI unterstützt Remote-MCP mit OAuth 2.0, PKCE und konfigurierbarer lokaler `redirectUri`. Offizielle Dokumentation: https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md#oauth-support-for-remote-mcp-servers . Dies bedeutet **nicht**, dass die normale Gemini-Android-App automatisch private MCP-Verbindungen anbietet. Für die CLI ist ein ausführbarer, für Browser/OAuth-Callbacks geeigneter Client nötig; Termux/Android-Unterstützung ist separat zu verifizieren.

## Berechtigungen: nur lesen
- Erlaubte neue OAuth-Scopes: `bob:products:read` und `bob:diagnostics:read`. Eigener OAuth-Code, eigenes Client-ID/PKCE, eigenes widerrufbares 28-Tage-Grant; keinerlei Kopie der ChatGPT-Tokens.
- Erlaubte Tools nach Eigentümerfreigabe: `bob_product_audit`, `bob_product_gaps`, `bob_diagnostics`, `bob_signal_history`, `bob_push_history`.
- **Ausgeschlossen:** `bob:phone:control`, `bob:termux:execute`, `bob:push:test`, Schreibzugriffe/SQL, Render-/Cloudflare-/Aiven-/GitHub-Adminrechte und echte DEGIRO-Orders. Diese Rechte werden für den Gemini-Client serverseitig **auch bei falscher Anwendungskonfiguration** abgewiesen.
- Die originale Besitzeranmeldung und separate Bestätigung (ggf. Passkey) bleiben Pflicht. HTTPS bis zum Bob-Server, OAuth-Tokens kurzlebig, Hashes im bestehenden internen Speicher, Rotation/Widerruf unverändert.
- Das derzeitige allgemeine OAuth-Freigabedatum **16.11.2026** bleibt unverändert. Eine Verlängerung benötigt einen eigenen geprüften Auftrag und eine erneute Freigabe. Der neue Client darf diese Grenze nicht umgehen.

## Eigene Gemini-Konfiguration – ohne Geheimnisse
Als Vorlage ist `docs/gemini-readonly-mcp-settings.json` im Repo enthalten. Die Datei kann in die **private** Gemini-CLI-User-Konfiguration `~/.gemini/settings.json` übernommen werden (vorhandene Einstellungen nicht blind überschreiben). Sie enthält den HTTPS-MCP-Endpunkt, die festen Lesetools, `trust:false` und die **exakte** `redirectUri`, aber keinerlei API-Keys, Cookies, Passwörter oder Tokens. Bei der tatsächlichen ersten Verbindung öffnet Gemini CLI den Browser zur Bob-Freigabeseite; der Eigentümer muss **selbst** ausdrücklich zustimmen.

Ein erfolgreicher Test muss belegen: Zweiter Gemini-Client registriert; PKCE/Besitzerfreigabe erfolgreich; `bob_diagnostics` mit originalem Zeitstempel ist lesbar; `bob:phone:control`, Termux, Push-Test und ein fremder OAuth-Callback sind tatsächlich blockiert; bestehender ChatGPT-Client weiterhin funktionsfähig und einzeln widerrufbar.

## Kosten und Privatsphäre
Für die OAuth-Client-Erweiterung selbst wird **kein zusätzlicher Cloud-Dienst** angelegt. Das bedeutet nicht, dass Google-KI-Verarbeitung kostenfrei oder vertraulich ist: Googles Free-Gemini-API kann übertragene Eingaben zur Produktverbesserung verwenden. Private Bob-Diagnosen, Broker-/Depotwerte oder Screenshots dürfen **nicht** automatisch an ein Google-Free-Modell gesendet werden, selbst wenn ein lokaler MCP-Client sie auslesen kann. Für solche Daten sind separat bestätigte Datenschutzbedingungen, Berechtigungen und die informierte Freigabe der betreffenden Daten erforderlich. Ein Free-Projekt darf nie automatisch auf Paid umgestellt werden.

## Stand weiterer Zugänge
- **GitHub-Code:** Die vorhandene Handy-/Actions-Zweitprüfung ist bereits funktionsfähig; Gemini erhält über den neuen MCP-Client **keine** zusätzlichen GitHub-Schreibrechte.
- **Render und Cloudflare:** bestehende Betriebszugänge von ChatGPT werden nicht weitergereicht. Für Gemini wäre eine neue minimal berechtigte Authentifizierung nötig; vorläufig besser über Bobs gefilterte Lesediagnosen arbeiten.
- **Aiven/SQL:** Ohne nachweislich konfigurierte separate Read-only-Datenbankrolle keine direkte Verbindung; keine ungeschützten SQL- oder Geheimnisexports.
- **DEGIRO/SnapTrade, Bob Handy/Termux:** Nicht Bestandteil dieses Zugangs. Handels- und Gerätekontrolle bleiben gesperrt.

**Abnahme:** `python -m unittest -v test_bob_oauth.py test_bob_oauth_db.py test_bob_mcp.py` und vollständige Bob CI. Ein grün getesteter PR ist noch **kein** produktiver Gemini-Login.
