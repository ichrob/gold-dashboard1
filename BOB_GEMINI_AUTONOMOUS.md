# Gemini bei Bob – sechs getrennte Erweiterungen (Arbeitsstand 11.11.2026)

**Wichtig:** Die hier beschriebenen neuen Fähigkeiten werden zunächst als
geprüfte PRs vorbereitet. Ohne erfolgreiche CI, Owner-Freigabe und Live-Abnahme
sind sie ausdrücklich NICHT als produktiv installiert zu betrachten.

## 1. Unabhängiger Gemini-Entwicklerweg

Neuer manueller Workflow: .github/workflows/bob-gemini-independent-draft.yml.
Nur der Repository-Besitzer ichrob kann ihn auf main starten. Er benötigt den
bestehenden GEMINI_API_KEY als GitHub-Secret, ein vom Besitzer bestätigtes,
unberechnetes Free-Projekt und die neue opt-in-Variable
BOB_GEMINI_DRAFT_PR_ENABLED=1. Ohne diese Voraussetzungen kein Modellaufruf.

Gemini erstellt einen einzigen Unified-Diff-Vorschlag aus einem öffentlichen
Issue und einer vorhandenen kleinen öffentlichen Datei. GitHub Actions prüft
Pfad, Quelle, Secrets und ob der Patch auf die aktuelle Datei passt.
Der Patch wird als INERTE Textdatei in gemini_proposals/ in einem eigenen
Branch und einem DRAFT-PR gesichert. Nie automatisch in Python/JS-Dateien
angewendet oder ausgeführt; kein Merge und kein Deploy.

Die PRs werden von github-actions[bot] angelegt, nicht von einer unabhängigen
GitHub-Identität des Gemini-CLI. Ein vollwertiger GitHub-Schreibzugang für
Antigravity erfordert eine separat vom Besitzer autorisierte GitHub-App oder
ein enges eigenes Konto. ChatGPT-Tokens niemals in Gemini oder Termux kopieren.

## Besitzerregel: gegenseitige Kontrolle grundsätzlich erlaubt (11.11.2026)

**Entscheidung des Besitzers:** ChatGPT und Gemini dürfen sich und Bobs
Entwicklungsergebnisse standardmäßig gegenseitig kontrollieren: Code,
öffentliche PRs, freigegebene Originaldaten-Diagnosen, Studien,
Simulationen, Regressionstests, Sicherheitsprüfungen und ihre eigenen
Prüfaussagen. Eine Kontrolle unterbleibt, wenn der Besitzer sie für
den konkreten Fall ausdrücklich verbietet. Das Verbot hat Vorrang vor
dem Standard, auch wenn die andere KI schon eine Freigabe empfohlen hat.

Für GitHub-PRs genügt ein **exakter neuer Kommentar des Besitzers**
`/bob-peer-review-off`; der spätere exakte Besitzerkommentar
`/bob-peer-review-on` hebt die Sperre wieder auf. Fremde Kommentare,
Bots und frei formulierte Zusätze sind keine Zustimmung. Fehlt der
vollständig verifizierbare Kommentarverlauf, wird nicht automatisch
geprüft. Eine bereits veröffentlichte Beurteilung wird durch spätere
Sperren nicht rückwirkend gelöscht. Für andere Fälle dokumentiert der
Reparatur-Owner das ausdrückliche Verbot im Arbeitsauftrag und
veranlasst keine weitere Weitergabe oder Prüfung.

**Gleiches Prüfungsrecht ist kein gleicher Zugang:** Es entsteht dadurch
weder ein Google-/GitHub-OAuth-Grant noch Zugriff auf private Broker-,
Depot-, Handy-, Termux-, Cloud- oder ChatGPT-Daten. Nur separat
berechtigte, bereinigte Read-only-Diagnosen sind zugänglich. Kein neuer
kostenpflichtiger Modellaufruf vor bestätigtem unbilled-Free-Projekt und
bestehenden Variablen/Secrets; ohne dies ist der Status
`review-authorized-but-not-run`, nie `review-completed`.

Jeder Fehlerfall hat weiterhin **genau einen schreibenden Reparatur-Owner**
(ChatGPT oder Gemini), damit nicht zwei parallele Fixes kollidieren.
Die jeweils andere KI kann standardmäßig unabhängig prüfen, muss
aber das ausdrückliche Veto respektieren. Weder gegenseitige Kontrolle
noch grüne CI erlauben automatische Merges, Deployments, reale Orders,
Archivlöschung oder Aufweichung der Sicherheitsregeln.

## 2. Automatische KI-Zusammenarbeit

Vorhandener Bob-Watchdog -> dedupliziertes GitHub-Issue ->
Reparaturwächter als einziger Code-Owner -> grüner PR-CI ->
optionaler unabhängiger Gemini-Review -> gesonderte Live-Abnahme.

PR #1543 ergänzt prospektive Studienwarnungen; PR #1544 behebt eine
beobachtete GitHub-Listengrenze und muss noch geprüft werden.
Die bestehende Gemini-Codeprüfung ist opt-in und liest nur öffentliche,
gefilterte Patches. Für automatische Reviews muss
BOB_GEMINI_AUTO_REVIEW_ENABLED=1 mit einem unbilled Free-Projekt bestätigt
werden. Sonst ist der Status ausdrücklich secondary-review-not-run.
Keine doppelt gestarteten KI-Reparaturwächter.

## 3. Paper-Simulationsprüfer

Das neue Diagnose-MCP-Werkzeug bob_simulation_audit liefert konservative
Status- und Coveragefelder aus dem bereits bereinigten Bob-Snapshot.
Inconclusive, collecting, partial und fehlende Originale bleiben offen.
Keine erfundenen Gewinne, Quotes, Ausstiege oder realen Broker-Fills.

## 4. Kleinere, gezielte Diagnoseansichten

bob_diagnostics_view nimmt nur feste Ansichten aus bereits bereinigten
Snapshot-Daten an. Jedes Listenfenster ist auf maximal fünf Einträge begrenzt,
jede Antwort auf 64 KB. Fehlende Evidenz wird als unavailable/partial
gekennzeichnet. Ein neuer Aufruf kann einen anderen Originalzeitpunkt haben;
Seiten ohne Zeitprüfung nicht als identischen Snapshot zusammenführen.
Keine neue öffentliche API oder zusätzliche Zugriffsrechte.

## 5. Unabhängige Qualitätskontrolle

Vorhandene CI, CodeQL und Reparatur-Nachweisprüfung bleiben maßgeblich.
Der Gemini-Codeprüfer und der neue lokale Sicherheits-Subagent geben nur
begrenzte Hinweise. Ein KI-Kommentar ersetzt keinen Regressionstest,
keinen Originalnachweis und kein produktives Deployment.

## 6. Drei spezialisierte Antigravity-Subagenten

Unter .agents/agents/ liegen:
- bob-source-investigator: Quellenzeit, Candle-Frische und Datenkonflikte
- bob-paper-study-auditor: virtuelle Einstiegs-/Ausstiegs- und Netto-Evidenz
- bob-security-reviewer: öffentliche Code-Patches, OAuth- und Risikoschutz

Jeder Subagent erhält nur lesende Codewerkzeuge, keine MCP-Vererbung und
keine automatische Shell-Ausführung. Der Hauptagent kann ausschließlich
bereinigte Daten explizit übergeben. Sichtbarkeit in Antigravity erst nach
Öffnen des GitHub-Repositories als Workspace oder gesonderter Installation
prüfen; ein bloßer Merge installiert diese Agenten nicht auf dem Telefon.

## Grenzen, Kosten und Schutz

Das Bob-Repository ist öffentlich: keine privaten Diagnosen, Depotdaten,
ISIN-Listen, Zugangsdaten, Rohlogs oder persönlichen Bilder in GitHub.
Google Free-Tier kann Daten für Produktverbesserungen verwenden; private
Diagnosen nur über die ausdrücklich bewilligte, minimale Read-only-Verbindung.
Keine bezahlte API-Fallback-Option, keine Echtgeldorders, keine
automatischen Merges, keine Stop-/KO-Lockerung, keine Archivlöschung.

## Abnahme

- PR-Tests einschließlich Security und CI nachweislich grün.
- Manueller Free-only-Draft-PR: echter, deduplizierter GitHub-Draft mit
  inertem Patch, unveränderter Produktionscode.
- Neue Diagnose-MCP-Tools: echter autorisierter Live-Aufruf und strenge
  Antwortgrößenkontrolle, kein Write-Scope.
- Antigravity /agents: drei Agenten erkennbar und wenigstens ein begrenzter
  unabhängiger Prüfbericht.
- Echte Studie -> genau eine deduplizierte Wächter-Übergabe -> Prüflauf
  mit dokumentiertem Gemini-Review oder ehrlich not-reviewed.
- Keine tatsächlichen Orders, keine ungeprüften Gewinne, keine Kosten.
