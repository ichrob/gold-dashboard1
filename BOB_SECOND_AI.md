# Bob: gemeinsamer KI-Arbeitsablauf mit kostenloser Zweitprüfung

## Ziel
Vorhandene Bob-Wächter, die laufenden ChatGPT-Reparaturaufträge und eine unabhängige
zweite KI werden an denselben GitHub-Fehlerfällen ausgerichtet. ChatGPT bleibt
Haupt-Reparaturentwickler, die zweite KI ist unabhängiger Prüfer.

## Ablauf nach Merge
1. Der bestehende unabhängige GitHub-Watchdog bleibt führend: kein zweiter Wächter,
   kein zusätzlicher Render-Dienst und keine zusätzliche Render-RAM-Last.
2. Nach erfolgreicher Watchdog-Prüfung erstellt bob_ai_coordination.py höchstens
   drei idempotente KI-Übergaben in vorhandenen offenen GitHub-Issues.
   Nur erlaubte Fehlercodes, nie private Logs, Zugangsdaten, Handel oder Rohkurse.
3. Die bestehenden ChatGPT-Reparaturwächter können diese Vorgänge anhand der
   verbundenen Diagnosezugänge weiter bearbeiten und einen PR erstellen.
   Ein Issue-Kommentar allein startet **kein ChatGPT-Modell automatisch**.
4. PRs für einen technischen Reparaturfall tragen genau eine Kennung
   im Body, z. B. BOB-123-scanner-unreachable. Der zusätzliche
   Bob-Reparatur-Nachweis-Workflow kontrolliert, ob das bekannte Issue passt
   und mindestens eine Regressionstest-Datei geändert wurde.
   Das ist KEIN Beleg für bestandene Tests; die normale Bob CI muss
   darüber hinaus erfolgreich laufen.
5. Nach erfolgreichem PR-CI-Lauf kann die zweite KI nach ausdrücklicher
   Free-Tier- und Auto-Freigabe einen unabhängigen Codeprüfkommentar erstellen.
   Zugelassen: nur nicht als Draft markierte interne PRs von ichrob mit
   genau einem gültigen Bob-Reparaturfall.
6. Kein eigenständiges Merge, Deploy, Echtgeldorder oder Änderung
   der Trading-/KO-/Stop-Risikoregeln. Nach genehmigtem Deploy ist ein
   unabhängiger Live-Nachweis erforderlich. KI-Meinung oder CI allein
   schließen keinen Fehler.

## Modell und Begrenzungen
Cloudflare Workers AI / @cf/zai-org/glm-4.7-flash.
Ein begrenzter Modellaufruf pro Prüfung ohne Retry und ohne kostenpflichtigen
Fallback. Nur bis zu fünf kurze gefilterte Ausschnitte öffentlicher
Pull-Request-Patches, keine private Datenbank, keine DEGIRO-Daten.
Ein Review pro Code-Commit, höchstens zwei Reviews pro PR pro UTC-Tag.
Unvollständige Kommentarhistorie oder unbekannte PR-Herkunft sperrt den Aufruf.

## Kosten-Schutz und Einrichtung
Cloudflare Workers Free enthält laut Anbieter 10.000 Neurons täglich kostenlos;
auf Workers Paid können darüber hinaus Kosten anfallen. Die aktuelle
Cloudflare-Verbindung erlaubt keine belastbare Abfrage des Account-Tarifs.
Daher ist das Modell ausdrücklich **deaktiviert**, bis der Tarif im Dashboard
als Workers Free bestätigt ist. Der Konfigurationsschalter allein kann
den externen Kontotarif nicht technisch erzwingen.

Nach erfolgreichem Review/Merge:
1. Cloudflare Dashboard: Workers Free nachprüfen, keinen Paid-Plan und
   keine AI-Gateway-Prepaid-Abrechnung für diese Verbindung verwenden.
2. Cloudflare-API-Token ausschließlich mit Workers-AI-Inference-Zugriff
   erstellen. Kein Passwort und keinen Token im Chat oder öffentlichen
   GitHub-Issue ablegen.
3. GitHub Settings > Secrets and variables > Actions:
   BOB_CF_AI_ACCOUNT_ID und BOB_CF_AI_TOKEN als Secrets setzen.
4. Nach verifiziertem Free-Tarif als Actions-Variable
   BOB_AI_FREE_ONLY = confirmed-workers-free setzen.
5. Für automatische Zweitprüfung zusätzlich separat
   BOB_AI_AUTO_REVIEW_ENABLED = 1 setzen. Ohne diesen zweiten
   Schalter bleibt nur der optionale manuelle Workflow.
6. Quota im Cloudflare-Dashboard beobachten, bei Tarifänderung
   die beiden Variablen deaktivieren.

## Qualität und Transparenz
- Offline Tests: python -m unittest test_bob_ai_coordination.py test_bob_ai_quality_gate.py test_ai_peer_review.py
- Normale Bob CI prüft darüber hinaus den bestehenden Python-/JS-Code.
- Bestehende technische Selbstheilung, Beweise und offene Issues bleiben
  führend. Die neue Koordination schließt keine Issues und gibt keine
  Produkt-, Markt- oder Orderwerte frei.
- Das Ergebnis ist eine unabhängige zweite Codeeinschätzung, keine Garantie
  einer richtigen Reparatur oder höherer Handelsrendite.
- Der ChatGPT-KI-Reparaturwächter bleibt die bestehende
  ChatGPT-Automation; dieser PR erstellt keinen neuen unbeaufsichtigten
  kostenpflichtigen ChatGPT-API-Executor.
