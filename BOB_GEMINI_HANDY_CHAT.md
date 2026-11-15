# Gemini in Bob Handy — lokaler Entwicklungszugang

## Bedienung

Bob Handy → **Mit Gemini an Bob arbeiten** → **Gemini verbinden**.
Auftrag schreiben oder mit dem Mikrofon der Android-Tastatur diktieren. Antworten,
Werkzeugstatus und einzelne Freigabefragen erscheinen in derselben Ansicht.
ChatGPT, ein ChatGPT-Wächter und eine kostenpflichtige Gemini-API sind für diesen
Weg nicht erforderlich. Der normale Google-Gemini-App-Chat bleibt separat.

## Voraussetzungen und tatsächliche Grenzen

- Persönliche, bereits angemeldete Antigravity CLI mit ACP (`agy acp`) in Termux.
  Der Handshake auf dem Besitzergerät hat am 11.11.2026 Version 1.5.5 und ACP v1
  bestätigt. Das allein beweist noch keinen abgeschlossenen Entwicklungsauftrag.
- Vorhandener Git-Arbeitsbaum `~/bob-gemini-work` mit dem exakten Bob-Origin
  `https://github.com/ichrob/gold-dashboard1.git`. Dateien werden beim Start weder
  ersetzt noch zurückgesetzt. Vor einem neuen Fix aktuellen main-Stand prüfen.
- `gh` ist auf dem Besitzergerät angemeldet; Repository-Schreibberechtigung wurde
  bestätigt. Ein tatsächlicher neuer Gemini-Push ist gesondert nachzuweisen.
- Bob-Diagnose-MCP ist separat konfiguriert. Ein echter erfolgreicher autorisierter
  Diagnoseabruf über Gemini ist noch nicht abgenommen.
- Render, Cloudflare und Aiven werden durch diesen Chat NICHT automatisch
  autorisiert. Bestehende ChatGPT-Verbindungen und Schlüssel werden nicht kopiert.
  Eigene Provider-Anmeldung/Minimalrechte bleiben erforderlich. Aiven vorzugsweise
  nur lesen; Deployments über den vorhandenen geprüften GitHub-/Render-Weg.
- Kostenloses persönliches Google-Kontingent vorausgesetzt. API-Key-/Vertex-Umgebungs-
  Fallbacks werden aus dem Agentprozess entfernt; kein Abrechnungsprojekt angelegt.
  Ein bereits kostenpflichtiges Google-Konto wird dadurch nicht kostenlos.

## Laufzeit

Ein lokaler App-Tipp startet den separaten ACP-Adapter mit höchstens zwei Stunden
Sitzungsdauer. Er ist unabhängig von der 20-Sekunden-ChatGPT-Wartung; deren Ablauf
wird nicht verlängert oder umgangen. Die neue Komponente wird ausschließlich aus
dem signierten APK geladen. Android kann Termux beenden. Bleibt die Chatansicht
länger als zwei Minuten ohne Statuskontakt (z. B. Bildschirm gesperrt), beendet der
Adapter die Sitzung inklusive Agentprozessgruppe. Kein 24/7-Dauerbetrieb versprochen.
Nach einer Unterbrechung werden Aufträge niemals automatisch erneut ausgeführt.
Ein neuer Start erzeugt einen neuen Chat; ältere Agentgespräche verbleiben ggf. in
Antigravity, werden aber hier nicht automatisch wiederaufgenommen.

## Sicherheitsgrenzen

- Nur 127.0.0.1; zufälliges 256-Bit-Sitzungsgeheimnis, nicht in URLs, Logs, Cloud,
  SharedPreferences oder Zwischenablage. Android-Ansicht ist nicht exportiert.
- Exakter Host, kein Browser-Origin, kein CORS; GET ausschließlich `/status`, POST
  ausschließlich `/prompt`, `/permission`, `/stop`. Kein generischer Shell-Endpunkt.
- Freitext wird als JSON über ACP übergeben, nie als Shell-/Python-Quelltext.
- Keine vererbten ACP-Client-Datei-/Terminalfähigkeiten. Antigravity führt seine
  eigenen Werkzeuge gemäß den bestehenden Berechtigungen aus. Freigabefragen
  werden vollständig angezeigt; Bob bietet nur einmal erlauben/ablehnen, keine
  globale automatische Genehmigung. Bei übergroßen Aufrufen nur ablehnen.
- STOPP im Chat sowie der zentrale NOT-STOPP beenden diese Sitzung; bereits
  abgeschlossene Änderungen oder entfernte Jobs werden nicht rückgängig gemacht.
- Antworten und Freigaben bleiben im App-/Adapter-Arbeitsspeicher. Kein Upload an
  Bobs Diagnose-/Pushserver. Google verarbeitet den Agentkontext gemäß dem eigenen
  Konto; keine Geheimnisse in Chat oder öffentlichen Issues ablegen.

## Abnahme

Offline: `python -m unittest -v test_bob_gemini_bridge test_android_stable_release_config`.
Android: bestehender Companion-Build und Android-Tests. Danach signierte Version
installieren, echtes persönliches Google-Login, eine harmlose Antwort, eine
Dateiänderung im separaten Branch, passenden Test und eigenen PR nachweisen.
Berechtigung erlauben/ablehnen und STOPP müssen zusätzlich auf Samsung funktionieren.
Ein grüner Build allein ist kein produktiver Funktionsnachweis.

Offizielle Schnittstelle: https://antigravity.google/docs/ide/extensions/acp
Protokoll: https://agentclientprotocol.com/protocol/v1/initialization
