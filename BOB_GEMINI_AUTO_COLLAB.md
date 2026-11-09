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

## Automatischer Modellwechsel-Schutz (vor 01.12.2026)
Google hat für `gemini-2.5-flash` eine automatische Weiterleitung ab 01.12.2026 angekündigt. Um unbemerkte Modell- oder Abrechnungsänderungen zu vermeiden, verweigert `gemini_peer_review_free.py` ab **01.12.2026 UTC** **alle** Gemini-Anfragen, selbst bei vorhandenen GitHub-Variablen. Nach erneutem Anbieter-/Preis-/Free-Projekt-Check und expliziter Freigabe muss zuerst ein geprüfter Nachfolge-PR den festen Modellnamen und diesen Sperrtermin aktualisieren. Keine Umgehung durch bloße Einstellungsänderung. `gemini-2.5-flash` wird bis dahin mit höchstens 1.024 Denk- und 2.500 Gesamtausgabetokens pro Aufruf angefragt; keine zusätzlichen kostenpflichtigen Anfragen.

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
