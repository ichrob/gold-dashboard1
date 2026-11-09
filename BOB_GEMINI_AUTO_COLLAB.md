# Google Gemini ↔ ChatGPT/Bob: gemeinsame GitHub-Zweitprüfung (ohne Chat-Kopieren)

**Status 09.11.2026: Vorbereitung als Draft-PR; noch NICHT aktiv.**
Keine Verbindung zu einer bestehenden Gemini-Handy-Unterhaltung. Der technische Zugang nutzt nach einmaliger Einrichtung die **Gemini Developer API** mit einem separaten API-Schlüssel, nicht die Gemini-App.

## Was konkret automatisch wird
1. Bobs bestehende ChatGPT-Reparaturwächter/Entwickler legen nachvollziehbare, begrenzte Reparatur-Pull-Requests mit Fallmarkierung an.
2. `Bob CI` prüft den Code; nur nach einem **erfolgreichen** PR-Lauf wird die neue separate GitHub-Aktion aktiv.
3. Der Gemini-Workflow liest ausschließlich die in `ai_peer_review.safe_files` freigegebenen **öffentlichen** PR-Patches (maximal fünf kleine Ausschnitte; sensible Textmuster gesperrt).
4. Gemini 2.5 Flash gibt höchstens drei unverbindliche Fehler-/Regressionstest-Hinweise ab; die Antwort steht als Kommentar am jeweiligen PR in GitHub.
5. Die ChatGPT-Reparaturwächter können diese GitHub-Kommentare beim nächsten normalen Reparaturdurchlauf prüfen und einen echten Code-Fix mit CI und späteren separaten Live-Nachweisen erstellen. Das ist **keine** direkte Synchronisierung von ChatGPT- und Gemini-Handy-Chats.
6. Keine automatischen Merges, Deployments, Orders, Brokerzugriffe, Archivlöschungen oder Änderung von Handels-/KO-/Stop-Regeln.

Die vorhandene Cloudflare-Workers-AI/Zweitprüfung bleibt unberührt. Sie ist **nicht Google Gemini**.

## Einmalige Einrichtung im Android-Browser (Besitzer selbst)
**Unbedingt vor Freigabe prüfen:** Google AI Studio muss ein **unberechnetes Free-Projekt** anzeigen, ohne aktiviertes Billing. Nachträgliches Aktivieren von Paid kann kostenpflichtig sein. Eine GitHub-Variable ist nur eine Selbstauskunft und **kann den Google-Abrechnungsstatus technisch nicht überwachen oder sperren**.

1. Im Android-Browser https://aistudio.google.com/api-keys öffnen, im eigenen Google-Konto anmelden. Prüfen, dass der verwendete API-Key ausschließlich mit einem unberechneten, kostenlos nutzbaren Projekt verbunden ist. Wenn dafür ein Zahlungsmittel/Billing/Upgrade verlangt wird: **abbrechen**.
2. Einen Gemini-API-Schlüssel im geeigneten Free-Projekt erzeugen. **Niemals den Schlüssel an ChatGPT, Gemini-Chat, Issues, PRs oder in eine Quellcodedatei senden.**
3. GitHub-Browser unter `ichrob/gold-dashboard1` → Settings → Secrets and variables → Actions → **Repository secrets** → New repository secret:
   - Name: `GEMINI_API_KEY`
   - Value: der Schlüssel (nur hier einfügen).
4. Im selben Menü unter **Repository variables** zwei Variablen neu anlegen:
   - `BOB_GEMINI_FREE_ONLY` = `confirmed-unbilled-free-project` — nur nach eigenständiger Prüfung des **unberechneten** Free-Projekts.
   - `BOB_GEMINI_AUTO_REVIEW_ENABLED` = `1` — erst nach Review/Merge und testbarem Funktionstest; bei Problemen/Wunsch zum Pausieren auf `0`.
5. Den separaten Draft-PR prüfen, Tests und GitHub Actions kontrollieren; erst danach zum Merge freigeben. Erst **ab Merge auf `main`** kann der Review-Workflow auf spätere passende Pull Requests reagieren.
6. Auf GitHub Actions → „Bob Gemini - unabhaengige kostenlose Zweitpruefung“ → Run workflow zum kontrollierten manuellen Test einen **öffentlichen** internen PR als Nummer angeben. Der normale automatische Modus verlangt einen aktuellen erfolgreich abgeschlossenen `Bob CI` PR-Lauf sowie gültige Reparaturfallmarkierung, autorisierten PR-Autor, gleichen Repository-Ursprung und einen Nicht-Draft-PR.

## Verifizierter Modellzugang und Ablaufdatum

Der erste Live-PR-Test am 09.11.2026 mit `gemini-2.5-flash` scheiterte HTTP 404. Googles Entwicklerteam dokumentiert eingeschränkten 2.5-Zugriff für neue Projekte und empfiehlt `gemini-3.8-flash` bzw. `gemini-3.5-flash-lite`. Nach dem 404-Wechsel auf Gemini 3.8 Flash scheiterte auch ein einzelner echter Prüfaufruf am festen 40-Sekunden-Limit (GitHub Action 42583856208, zweiter Lauf, Stage model-generate). Für kurze, wiederholbare Codegegenprüfungen verwenden wir nun **ausschließlich Gemini 3.5 Flash-Lite**, das Google ausdrücklich für geringe Latenz und Subagent-Aufgaben vorsieht, mit separat bestätigtem Free-Projekt. Google weist im aktuellen Standard-Free-Tier kostenlose Ein- und Ausgaben aus. Das ist **keine technische Prüfung der Kontoabrechnung**.

Die Konfiguration verwendet `thinkingLevel=minimal`, maximal 1.800 Gesamtausgabetokens, einen begrenzten Timeout von 55 Sekunden und genau einen API-Aufruf ohne Retry oder Paid-Fallback. Zur erneuten Free-/Modell-/Providerprüfung verweigert der Code ab **01.01.2027 UTC** alle Gemini-Anfragen, bis ein geprüfter Folge-PR Modell und Sperrtermin aktualisiert. Eine Änderung der GitHub-Variablen allein hebt die Sperre nicht auf.

Die reine GitHub-Codeprüfung benötigt keinen direkten Chat-Zugriff auf die Gemini-App.

## Kosten-/Sicherheitsgrenzen
- Google beschreibt `gemini-2.5-flash` in der Developer API mit begrenztem **Free Tier**, inklusive Nutzung der Free-Eingaben zur Verbesserung von Google-Produkten. Ausschließlich gefilterte **öffentliche Quellcode-Patches** senden. Keine privaten Screenshots, DEGIRO-/Depotdaten, Passwörter oder Bob-Diagnose-Originale.
- Nur **ein** KI-Aufruf nach Nachweis- und Duplikatprüfung; höchstens zwei Gemini-Kommentare pro PR und UTC-Tag und einer pro Commit; keine providerseitigen Wiederholungen/keine kostenpflichtigen Modell-Fallbacks.
- **Keine Preisgarantie durch Code:** Wenn das gleiche Google-Projekt nachträglich bezahlt wird, kann selbst das unveränderte Skript Kosten verursachen. Für strikt 0 zusätzliche Kosten darf das Google-Projekt nie zu Paid wechseln. Bei Tarifunsicherheit Workflow-Variable `BOB_GEMINI_AUTO_REVIEW_ENABLED=0` und ggf. API-Schlüssel widerrufen.
- CI/Review ist ein Hinweis, weder Erfolgsgarantie noch Beweis für Produkt-/KO-Daten oder Gewinne.
- GitHub öffentlich: Kommentare und Diffs sind öffentlich sichtbar. Der Workflow prüft Originalautor und interne Repo-Herkunft, verwirft Drafts und nicht freigegebene Reparaturfälle im automatischen Modus.
- Die frühere **kostenlose Consumer-Version** von Gemini Code Assist auf GitHub wurde laut Google am **17.07.2026 abgeschaltet**. Deshalb wird sie hier nicht als angeblich kostenloser neuer Anmeldungsweg empfohlen.

## Kontrolle und Rückweg
- `python -m unittest -v test_gemini_peer_review_free.py`
- CI: `.github/workflows/ci.yml` führt die neuen Unit-Tests nach Merge bzw. im PR aus.
- Ein fehlender Key/Opt-in -> kein Modellaufruf; Gemini-Antworten erscheinen als GitHub-PR-Kommentar mit Marker `BOB_GEMINI_REVIEW_V1`.
- Rückweg: GitHub Actions Variable auf `0` oder Actions-Workflow deaktivieren, API-Key widerrufen. Keine andere KI/Worker wird damit umkonfiguriert.
- Bestehender ChatGPT-Reparaturwächter kann nach erfolgter Aktivierung die PR-Kommentare lesen; ob er sie **tatsächlich** in einem Lauf berücksichtigt, muss gesondert durch einen dokumentierten Reparaturfall belegt werden. Keine automatische ChatGPT-Gesprächssynchronisation.

Quellen: https://ai.google.dev/gemini-api/docs/pricing ; https://aistudio.google.com/docs/get-started ; https://developers.google.com/gemini-code-assist/docs/deprecations/consumer-code-review
