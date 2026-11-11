# Bob → Gemini: unabhängige Projektübernahme und aktueller Arbeitsleitfaden
**Stand der Zusammenstellung:** 9. November 2026. **Kein automatischer Live-Status.**

Dieses Dokument ermöglicht Google Gemini/Antigravity den eigenständigen Einstieg in Bob ohne Zugriff auf ChatGPT-Privatchats. Der vollständige und jeweils aktuelle Quellcode, die dokumentierten Entscheidungen, aktuellen Issues, PRs und CI-Läufe befinden sich im GitHub-Repository: https://github.com/ichrob/gold-dashboard1. Es ist **öffentlich**. Bitte zuerst `GEMINI.md` lesen.

## 1. Auftrag und Grenzen
Bob ist ein privater, mobil genutzter Gold-Intraday-Trading-Assistent für die **Analyse** von Gold und die **Auswahl** von DEGIRO-Hebel-/KO-Produkten. Er beobachtet Datenquellen, bewertet Trend/Momentum/Fibonacci/MTF/Volatilität/Marktstruktur, erstellt Frühwarnungen, Stop-/Zielvorschläge, Produkt-Rankings und Paper-Simulationen. **Echte Orders sind nicht aktiviert**; Quellcode für theoretische/assistierte Orderabläufe ist kein Beweis einer zulässigen automatischen Orderausführung.

Gemini soll als **eigenständiger** zweiter Entwickler Probleme finden, reproduzierbare Regressionstests schreiben, begrenzte Pull Requests vorschlagen und bestehende Lösungen unabhängig gegenprüfen. Gemini ist weder von ChatGPT abhängig noch automatisch in dessen private Zugänge eingebucht. Zusammenarbeit über GitHub-Issues, Branches, PRs, CI-Resultate und datensparsame Prüfbelege.

## 2. Architektur
| Bereich | Vorhandener Weg | Wichtige Grenze |
| --- | --- | --- |
| Code und Testorchestrierung | GitHub `ichrob/gold-dashboard1`; `.github/workflows/` | PR und tatsächlichen CI-Status prüfen |
| Analyse/Backend | Render `bob-private-scanner` | Kein Produktivzugriff durch öffentliche Codekenntnis |
| Push/Background | Render `bob-push-service` | Push-Annahme ist nicht bewiesene Anzeige auf dem Samsung |
| Persistenz | PostgreSQL/Render, historischer Replay, verschlüsseltes Archiv | Nicht aus GitHub öffentlich lesbar |
| Mobil | Android „Bob Handy“, Bob-Oberfläche / „Bob Zentrale“ | DEGIRO-Automatisierung und Screenshot-Erfassung benötigen echte Handy-Abnahme |
| DEGIRO/Depot | Screenshot-/Produktnachweise; SnapTrade read-only | Kein verlässlicher automatischer Broker-Orderzugang oder echte Fills |
| KI-Zweitprüfung (bestehend) | GitHub OIDC → Cloudflare Workers Free → Workers AI/Qwen | Bereits eine **andere KI**; nicht Gemini |
| KI-Entwicklung (neu) | Google Gemini via Antigravity oder Gemini-Web-App | Eigenes Google-Login, eigene Autorisierung und Rechte |

Die maßgebliche technische Beschreibung steht im jeweiligen aktuellen Dokument, nicht in diesem Überblick.

## 3. Funktionale Regeln und fachliche Anforderungen
- **Goldwerte:** XAU/USD Spot als eigene Preisidentität; CFD, Future und Produktscheine niemals still vermischen. Der bevorzugte Spot-Quellpfad und Ersatzquellen stehen in `DATA_FALLBACK_POLICY.md`. Ein abrufbarer Endpunkt beweist keine Frische; ursprüngliche Provider-Uhrzeit behalten.
- **Kerzen:** 1m/5m/15m/30m/1h und 4h-Kontext. Nur valide echte OHLC bzw. vollständige, belegbare Aggregationen. EMA20/50/200, MACD, RSI, ADX/DMI, ATR, Bollinger und Fibonacci kontextgerecht und mit Mindesthistorie. Unvollständige DMI-/EMA200-Historie nicht als „bestätigt“ deuten.
- **Signale:** Frühwarnung vor Hauptsignal, MTF-Prüfungen und Session-Regeln; Trendwechsel nur mit belegten aktuellen Schlusskerzen. Neutral/Abwarten ist eine echte Entscheidung. Intraday-Anforderungen und die jeweils gültige Version aus Code und `INTRADAY.md` ermitteln; im Code kann die jüngere Regelrevision maßgeblich sein.
- **Produkte:** Eine vom Marktmodus abhängige Rangliste (LONG oder SHORT; bei Abwarten keine erzwungene Liste). Richtige ISIN, Richtung, KO, Basis, Geld/Brief mit Zeit, Währung, Bezugsverhältnis, Handelsplatz. Rechenwerte transparent kennzeichnen; ohne Originalnachweis keine Freigabe. Kein Faktorprodukt und keine erzwungene Top-3.
- **Risikomanagement:** Stopp, Ziel, ATR/Fibonacci, CRV, Nachziehen ohne Aufweichen des Stops; KO-Abstand und Produktbelege zentral. Echtgeldorders nicht durchführen.
- **Paper-Modelle:** Bestehende 800-€, 1.000-€-Frühwarn-/Normal- und 2.000-€-Risiko-Ansätze sowie historische Varianten; genaue aktive Anzahl aus aktuellem System lesen. Erfolg nur aus reproduzierbaren Original-Entries/Exits und tatsächlichen Gebühren/Spread/Slippage-Betrachtungen ableiten. Keine Rendite aus fehlenden Fills schätzen.
- **Bedienung:** Samsung/Bob-Handy: ein möglichst einfacher Start, DEGIRO-Suche, „Hebelprodukte“, 10 Produkte samt Belegen; keine Behauptung einer abgeschlossenen End-to-End-Erfassung, bevor der echte App-Lauf es zeigt.
- **Speicher:** Nutzerziel 5 GB, aktuell genutzte Daten und notwendige Originale behalten; nur alte nicht benötigte Inhalte archivieren, kein unkontrolliertes Löschen.

## 4. Status zum Zusammenstellungszeitpunkt – nicht mit Live-Zustand verwechseln
Am 09.11.2026, etwa **07:30 Uhr Zürich** (06:30 UTC), lieferte der vorhandene read-only-Bob-Diagnosezugang einen **partiellen** Betriebszustand. Spot-Eingang und wichtige 1m-/5m-Kerzen wurden beobachtet; 15m-/1h-DMI war wegen nicht ausreichend zusammenhängender Originalkerzen unvollständig; mehrere Produkt-Originalnachweise waren offen. Die Analyse befand sich im Vorbereitungsfenster vor 08:00 Uhr. Das beweist weder einen allgemeinen Dienstausfall noch Handelsfreigabe oder Live-Rentabilität. Bob meldet keine aktiven echten Orders.

Offene GitHub-Themen (Zeitstand separat prüfen): `#726` fehlende Produktstammdatenbelege, `#724` KO-Gültigkeitsnachweis, `#1329` vorsichtige Speicher/Archiv-Optimierung. Am 09.11.2026 war die OCI-Always-Free-OCR-Vorbereitung `PR #1474` noch ein **Draft** ohne real bereitgestellte Oracle-VM oder private Screenshot-Übertragung. Eine auf GitHub geprüfte virtuelle ARM64-Abnahme ist keine produktive OCI-Installation.

Die Cloudflare-KI-Zweitprüfung war nach `PR #1471` anhand ihres tatsächlichen Workflow-Ablaufs getestet; sie nutzt laut `BOB_CLOUDFLARE_FREE_OIDC.md` **Workers AI/Qwen**. Sie stellt keine Google-Gemini-Verbindung dar. Vor jedem weiteren Statusurteil aktuelle GitHub-PRs, Action-Ergebnisse, Render-Deploys und autorisierte Bob-Diagnosen neu prüfen.

## 5. Wegweiser im Repository
| Thema | Startquelle |
| --- | --- |
| Grundregeln für KI-Agenten | `GEMINI.md` |
| Intraday-Logik und Versionsgeschichte | `INTRADAY.md`, Strategiecode |
| Kurse, Fallbacks, Frische und Rechenwerte | `DATA_FALLBACK_POLICY.md` |
| Produktwahl und Freigaben | `PRODUCT_RANKING.md`, `DEGIRO_PRODUCT_AUDIT.md`, `BROKER_SIGNAL_ROUTING.md` |
| Handy/DEGIRO | `DEGIRO_IMPORT.md`, `ANDROID_DIAGNOSTICS.md`, `DEGIRO_AUTO_CATALOG.md` |
| Paper-Simulation | `PAPER_SIMULATION.md`, `BOB_ENTRY_EXIT_COMPARISON.md`, `BOB_TEST_OVERVIEW.md` |
| Push, Stop und Ziel | `PUSH_RULES.md`, `STOP_TARGET_AUDIT.md` |
| Speicher/Archiv/Restore | `BOB_KNOWLEDGE_STORAGE_POLICY.md`, `BOB_DRIVE_ARCHIVE.md`, Issue `#1329` |
| Zentrale/Diagnosen | `BOB_ZENTRALE.md`, `BOB_OPERATIONS_SUMMARY.md`, `DIAGNOSTICS_READ_ACCESS.md` |
| Unabhängige vorhandene KI | `BOB_SECOND_AI.md`, `BOB_CLOUDFLARE_FREE_OIDC.md`, `.github/workflows/bob-second-ai-review.yml` |
| Testläufe und Schutzgates | `.github/workflows/ci.yml`, `bob-risk.yml`, `bob-codeql-security.yml`, `bob-repair-evidence-gate.yml` |

Einige Dokumente protokollieren historische Designversionen; aktueller Code, aktuelle Konfiguration und reale Telemetrie haben Vorrang. Dateinamen sind Einstiegspunkte, keine Garantie, dass jeder beschriebene Prototyp produktiv läuft.

## 6. Zwei praktische Wege für Gemini – getrennt von ChatGPT
### A. Sofort: Gemini-Web-App zum Verstehen und Prüfen
1. Im eigenen Google-Konto https://gemini.google.com öffnen.
2. Diesen Onboarding-Text oder den GitHub-Link bereitstellen und Gemini ausdrücklich auffordern, `GEMINI.md` und die Quellen **selbst** zu lesen und seine Zugriffsgrenzen zu nennen.
3. Bei Verwendung der offiziellen GitHub-Import-Funktion: derzeit **nur am Computer**; sie erstellt einen **nicht automatisch synchronisierten Snapshot**. Nach neuen GitHub-Commits erneut importieren. Auf Android nicht als automatisch verbunden darstellen.
4. Ohne autorisierte Schreib-/Laufzeitwerkzeuge kann der Gemini-Chat Fragen beantworten und Code vorschlagen, aber nicht selbstständig Render/DEGIRO bedienen oder PRs liefern.

### B. Für eigenständige echte Entwicklungsarbeit: Antigravity
Google empfiehlt für kostenlose private Konten seit Juni 2026 **Antigravity CLI** statt der früheren `gemini` CLI. Offizielle Schritte: https://antigravity.google/docs/getting-started?tab=cli und https://www.antigravity.google/download. Unterstützte Arbeitsumgebungen offiziell Windows, macOS und Linux; **Termux/Android allein ist nicht offiziell zugesichert**.

1. In einer unterstützten Umgebung eigenständig bei Google anmelden und `ichrob/gold-dashboard1` als Git-Arbeitsverzeichnis öffnen/klonen.
2. Antigravity installieren/starten; es liest die `GEMINI.md` im Projektstamm als permanente Workspace-Regel. Keine Tokens in Prompt, Chat, Screenshots, Dateien oder GitHub-Historie.
3. Für Schreibarbeit GitHub **mit minimalem Repo-Zugriff** autorisieren und den sicheren Modus mit Bestätigung für Schreibaktionen nutzen; keine automatisch ausgeführten Shell-/Netzwerk-/Deploy-Aktionen.
4. Ersten Auftrag: „Untersuche Issue #726 ausschließlich anhand öffentlicher, bereits freigegebener Nachweise; baue einen reproduzierbaren Regressionstest und einen Draft-PR. Keine echten Produktwerte, keine Änderung der Handelssperre, kein Merge/Deploy.“
5. Erst nach erfolgreich geprüften PRs über zusätzliche read-only-Diagnosemöglichkeiten reden. ChatGPT-Connectoren werden **nicht** übertragen.

## 7. Privatsphäre und Kosten
Die GitHub-Codebasis ist öffentlich, doch Bob-/Broker-/Depotkonten, Originalbilder, Telemetrie und Wiederherstellungsschlüssel sind es nicht. Die freie Google-Gemini-API kann nach Googles Pricing-Angaben Eingaben zur Produktverbesserung verwenden. **Daher für den kostenlosen Einstieg nur öffentlichen und bereinigten Code teilen**, bis für mögliche private Daten eine passende Datenschutz-/Berechtigungslösung entschieden wurde.

Weder Cloud-Billing noch kostenpflichtige APIs automatisch aktivieren. Ein Free-Tier-Kontingent ist keine Garantie für unbegrenzte Nutzung und kein Freibrief für bezahlte Überschreitung.

## 8. Musternachricht für den ersten Gemini-Dialog
> Du bist der unabhängige zweite KI-Entwickler von Bob. Nutze https://github.com/ichrob/gold-dashboard1 und beginne mit GEMINI.md sowie BOB_GEMINI_ONBOARDING.md. Verifiziere eigenständig den neuesten main-Commit, Issues, PRs und abgeschlossene CI-Läufe. Erkläre mir knapp Bobs Architektur, echte Handelsgrenzen, Datenqualitätsprobleme und welche Zugriffe du tatsächlich hast. Keine Passwörter, keine Echtgeldorders, keine produktive Änderung, keine neuen Kosten. Schlage zuerst einen begrenzten, testbaren Fehlerfall vor. Erfinde keine aktuellen Betriebswerte.

## 9. Selbsttest nach Einrichtung
Gemini soll ohne ChatGPT im selben Chat folgende Fragen quellengestützt beantworten:
- Was ist der **letzte** Commit auf `main`? Welches konkrete CI-Ergebnis gehört dazu?
- Wie unterscheiden sich Gold-Spot, CFD-Kerzen und DEGIRO-Produktkurs? Welche Originalbelege fehlen in `#726`?
- Warum sind grüne CI und ein KI-Kommentar kein Nachweis für erfolgreiche Paper-Simulation oder echte Order?
- Wie schreibt Gemini einen eigenen Draft-PR, ohne eine bestehende Reparatur zu überschreiben?
- Welche Informationen kann Gemini **nicht** ohne zusätzliche Berechtigung sehen?

Erst wenn diese Fragen mit Links und sauber benannten Grenzen beantwortet sind, gilt die **Wissensübernahme** als praktisch bestanden. Die echte eigenständige Entwicklungsfähigkeit ist erst durch einen getrennt bestätigten Test-PR belegt.

## 10. Direkter Entwicklungsauftrag und Zugangsübersicht (11.11.2026)

Der Besitzer möchte mit Gemini selbstständig an Bob arbeiten und seine Wünsche
in Programmänderungen umsetzen lassen. Gemini soll vorhandene Werkzeuge prüfen
und innerhalb des konkreten Nutzerauftrags nutzen, statt pauschal nur Code zum
manuellen Kopieren anzubieten. Diese Erlaubnis schafft allein keine technische
Verbindung. Bereits erteilte, passende Nutzerfreigaben berücksichtigen; fehlt ein
Werkzeug oder Login, den konkreten fehlenden Zugang nennen. Nicht behaupten,
der Gemini-Android-Chat besitze automatisch die Rechte eines Actions-Jobs,
Antigravity oder der ChatGPT-Verbindungen.

| Zugang | Einstieg | Nachweis und Grenze |
| --- | --- | --- |
| Öffentlicher Code, Issues, PRs und CI | https://github.com/ichrob/gold-dashboard1 | Mit eigenen verfügbaren Lese-/Webwerkzeugen aktuellen Stand prüfen; Wissen aus einem Chat ist kein Live-Abruf. |
| Gemini-Codeprüfung / Entwicklungsvorschlag | BOB_GEMINI_MOBILE_DEVELOPER.md; .github/workflows/bob-gemini-free-review.yml; .github/workflows/bob-gemini-mobile-developer.yml | Separater API-/Actions-Weg; öffentliche Kommentare sind nachgewiesen. Keine Übertragung dieses Zugangs an die Gemini-App. |
| Separater Entwurfs-PR | BOB_GEMINI_AUTONOMOUS.md; .github/workflows/bob-gemini-independent-draft.yml | Opt-in und Free-only-Gates; nur inert gespeicherter Patch. PR #1563 war bei Prüfung am 11.11.2026 noch offen, ungemergt und konfliktbehaftet. Kommentarstart daher nicht als fertig ausgeben. |
| Eigenständiges Programmieren, Testen und GitHub-Schreiben | Antigravity im Bob-Arbeitsverzeichnis; BOB_ANTIGRAVITY_TERMUX.md | Lokale Installation ist historisch belegt; aktueller Login, Repository, Testausführung und eigener GitHub-Schreibzugang müssen separat geprüft werden. |
| Private Bob-Diagnosen | https://bob-private-scanner.onrender.com/mcp; BOB_GEMINI_MCP_READONLY.md | Eigener OAuth-Grant und erfolgreicher Werkzeugaufruf nötig; bestehende Vorbereitung ist kein bestätigter Live-Zugang. |
| Render | bob-private-scanner und bob-push-service | Eigene authentifizierte Render-Verbindung erforderlich. ChatGPT-Verbindungen sind kein Gemini-Zugang; Deploymentstatus gesondert prüfen. |
| Cloudflare / Aiven / Archiv | Vorhandene Projektanleitungen und getrennte Kontoverbindungen | Kein direkter Gemini-Zugriff durch die Projektrolle nachgewiesen; keine Tokens aus anderen Clients übernehmen. |
| Bob Handy / Termux | Nutzergeöffnete Wartungssitzung | Sitzung muss aktuell online sein. Beim Abruf am 11.11.2026 um 17:28 Zürich war sie abgelaufen/offline. Das ist kein dauerhafter Zustand. |
| DEGIRO / SnapTrade | Bestehende Produktnachweise bzw. getrennte Leseberechtigung | Kein automatisch übertragener Depot-/Gerätezugang; keine Echtgeldorders. |
| ChatGPT-Chats / Aufgaben | Keine automatische gemeinsame Sitzung | Gemeinsamer Projektstand über Repository und belegte Ergebnisse; keine Kenntnis privater Chats behaupten. |

**Erster Schritt in jeder Gemini-Umgebung:** Eigene tatsächlich angebotene
Werkzeuge auflisten; aktuellen main-Commit lesen; relevante offene Arbeit prüfen.
Mit vorhandenen Schreib-/Testwerkzeugen einen konkret beauftragten kleinen
Änderungsfall im eigenen Branch bis zum geprüften PR bearbeiten. Ergebnis mit
Commit, Tests und Link belegen. Falls der aktuelle Chat keine solchen Werkzeuge
hat, den verfügbaren Actions-/Antigravity-Weg und genau den fehlenden Schritt
nennen. Keine Passwörter oder Tokens im Chat anfordern. Nutzerziele sind
kostenfreier Betrieb, möglichst wenig Handy-Bedienung und überprüfbare Ergebnisse.

Diese Projektanweisung ist keine Zustellbestätigung: Erst wenn Gemini sie
tatsächlich gelesen und seinen Werkzeugtest ausgeführt hat, ist die Übernahme in
der jeweiligen Gemini-Sitzung nachgewiesen.
