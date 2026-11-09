# Gemini auf dem Android-Handy: kostenlose Entwickler-Vorschläge

**Status 09.11.2026:** Der bestehende Gemini-Free-Code-Review hat einen echten Kommentar in PR #1484 erstellt. Dieser zusätzliche **manuell auslösbare** Entwicklerlauf ist erst nach Merge dieses PR auf `main` nutzbar. Ein erfolgreicher CI-Lauf und ein anschließender echter Test sind noch erforderlich.

## Funktionsumfang
- Android/Chrome oder GitHub-App steuert `GitHub Actions` auf einem kostenlosen Standard-Runner des **öffentlichen** Projekts `ichrob/gold-dashboard1`.
- Ein einzelner öffentlicher GitHub-Issue-Auftrag und eine kleine bereits vorhandene öffentliche `.py`-/`.md`-Datei dienen als Kontext.
- Separates Google Gemini 3.5 Flash-Lite erstellt genau **einen** kleinen Code-/Regressionstest-Vorschlag als öffentlicher Kommentar direkt im Issue. Die bestehende `GEMINI_API_KEY`-Secret und Free-only-Variable werden wiederverwendet; kein zusätzliches Abo oder Server.
- **Weder führt Gemini Code aus, noch schreibt Gemini eine Repository-Datei, öffnet eigenmächtig PRs, merged, deployed, tradet oder liest private Bob-/Render-/DEGIRO-/Termux-/Cloudflare-Zugänge.** Die unabhängige ChatGPT-Reparaturprüfung kann den konkreten Kommentar später sicher beurteilen und in einem eigenen PR übernehmen.
- Für einen zweiten echten Entwickler mit unabhängigem Schreib-/MCP-/Serverzugang sind zusätzliche eigene Autorisierung, getrennte OAuth-Clients, Minimalrechte und Audit nötig: siehe Issue #1497.

## Einmalige Kostenprüfung auf dem Handy
1. In https://aistudio.google.com/api-keys beim verwendeten Google-Projekt **Free** und **ohne Abrechnung/Billing** kontrollieren. Wenn Paid/Upgrade/Zahlungsmethode benötigt wird: abbrechen. Die GitHub-Variable ist *keine* externe Kostenbremse.
2. Unter GitHub → Repository → Settings → Secrets and variables → Actions den vorhandenen, **niemals veröffentlichten** Secret `GEMINI_API_KEY` und die Variable `BOB_GEMINI_FREE_ONLY=confirmed-unbilled-free-project` kontrollieren. Nicht in Issues oder Chats einfügen.
3. Es gibt keinen automatischen Paid-Fallback und keine Retries. Der Code stoppt ab **01.01.2027**, bis Modell/Kosten erneut geprüft sind. Jede neue Ausführung erfordert einen bewussten Klick.

## Auf dem Android-Handy benutzen
1. GitHub → `ichrob/gold-dashboard1` → **Issues** → **New issue**; nur einen konkreten, öffentlichen Codefehler beschreiben. Keine persönlichen Daten, Logins, Broker-Bilder, Depotwerte oder Schlüssel.
2. Die Issue-Nummer notieren, zum Beispiel `1497`. Eine **existierende kurze Codedatei** auswählen, z. B. `gemini_peer_review_free.py` oder `GEMINI.md`. Der Quelltext muss klein (maximal 6.500 Zeichen) und öffentlich/unverdächtig sein.
3. GitHub → **Actions** → **Bob Gemini - Handy-Entwickler (kostenlos, Vorschlag)** → **Run workflow**. `main`, Issue-Nummer und Dateipfad eintragen → Run workflow.
4. Nach dem Lauf beim **gleichen Issue** den Kommentar `Gemini · Handy-Entwicklerentwurf` lesen. Er enthält einen Code-Vorschlag und Testideen. Kein Kopieren zwischen KI-Chats erforderlich.
5. Die unabhängige Reparaturkontrolle lässt daraus nötigenfalls einen geprüften Branch/PR mit CI und Live-Abnahme entstehen. Ein Kommentar ist noch **keine** tatsächliche Programmänderung.

## Sicherheits- und Leistungsgrenzen
- Eigentümerprüfung (`ichrob`), nur offene Issues, feste öffentliche Repo-URL, streng validierte Dateipfade, Dateigrößenlimit, einfache Geheimnisfilter und Kommentar-Deduplizierung.
- Höchstens 2 Vorschläge pro Issue/UTC-Tag und 1 pro unverändertem Issue-Datei-Stand; kein Modellaufruf ohne Free-Variable und gültigen geheimen API-Key.
- Modelleingaben sind externe Datenverarbeitung. Google Free Tier kann sie laut API-Bedingungen zur Produktverbesserung verwenden. Deshalb nur bereits öffentliche, bereinigte Inhalte eingeben.
- GitHub Actions Standard-Runner für öffentliche Repositories sind kostenlos. Das garantiert nicht, dass ein Google-Projekt kostenlos ist, sobald dort Billing aktiviert wird.
- Android hat hier **keine lokale Gemini-CLI/Antigravity-Installation nötig**. Der Server führt den Workflow aus; Browser/App ist nur die Bedienoberfläche.
- Kein Live-Zugriff auf die private ChatGPT-Verbindung; OAuth-Redirect des vorhandenen Bob-MCP ist momentan nur auf ChatGPT festgelegt.

**Fehlersuche:** `Actions` → betreffenden Lauf → Schrittname und sicheren Fehlercode prüfen; keine Secrets kopieren. Ein nicht erfolgreicher Kommentar-Test ist offen zu melden, nicht als erfolgreich auszugeben.
