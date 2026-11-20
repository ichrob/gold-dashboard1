# Bob – vorhandenen ISIN-Leser wiederverwenden und Stop-Loss-Simulation getrennt halten

## Nachweis und Regressionsursache

- **Referenz**: die veröffentlichte Android-Version `bob-android-v10930` (17.11.2026). Der produktive Empfänger hat für die angeforderte ISIN `DE000FB0A490` ein echtes Leseergebnis `COMPLETE` mit Geld, Brief, Anzeigezeit und Hebel bestätigt. Die vorhandene semantische Suche, Tastatur- und Produktnavigation bleiben die Grundlage.
- **Aktuelle Fehlerstrecke**: Wiederholt nur 9/10 vollständig verifizierte Gold-Produktzeilen aus drei Bildern; getrennte OCR-Speicherfehler. Der Server darf einen unvollständigen Batch weiterhin nicht für Ranking/Handel freigeben.
- **Android-Problem**: Bei der quarantänierten lokalen ISIN-Recherche liegt die auf dem Gerät bereits erfasste Goldliste nach dem Scrollen häufig ohne sichtbares EditText im Accessibility-Baum vor. Der bisherige Rückscroller erforderte unnötig zehn lokal sichtbare Identitäten **auch für einen rein lesenden Scroll**, sodass die lokal bekannte Suche wiederholt `PROTECTED_ORDER_CONFIRM` oder `SEARCH_GUARD_INPUT_COUNT` erreichte.
- **Änderung**: `quarantinedGoldReturnScrollTarget` erlaubt nur in einem bereits vom Besitzer gestarteten, entsperrten, exakten DEGIRO-Fenster ein isoliertes `ACTION_SCROLL_BACKWARD` auf der aktuellen Gold-Liste mit 1–10 **tatsächlich lokal gesehenen, validen** ISINs. Es überträgt keine Liste, setzt keinen Kurs und betätigt kein Order-/K/V-/PIN-/Passwort-Element. In `continueLocalGoldResearch` erfolgt danach eine frische, unveränderte Prüfung über den vorhandenen `localResearchDecision`/ISIN-Leser. Die 10/10-Serverfreigabe bleibt zwingend für verifizierte Produktlisten.
- **Sicherheit**: Ein isolierter, exakt geprüfter globaler `Order platzieren`-Launcher darf **nur** bei der Entscheidung über eine Liste ignoriert werden. Echter Bestätigungs-/Preis-/Mengen-/Orderart-Dialog sowie unerkannte Eingaben, doppelte Felder, andere App, anderer Fensterbezeichner, Sperrbildschirm und verlorene Sitzung bleiben blockiert.

## Frühere Stückzahl-/Stop-Loss-Arbeit – PR #1790

- Separat erhaltener Entwurf: https://github.com/ichrob/gold-dashboard1/pull/1790 .
- Der Erfolg der damaligen Emulator-/Mocktests **war keine reale Broker-Ausführung**.
- In dieser Änderung wurden nur die bestehenden reinen Kotlin-Dateien `StopLossPrefillPolicy.kt` und `StopLossOfflineSimulation.kt` sowie ihre JVM-Tests aus PR #1790 übernommen.
- Sie prüfen offline `BOB-STOP/1`, gültige EUR-ISIN, Stoppreis in Cent, positive Stückzahl, Ablaufzeit, Verkaufseite, Stop-Loss-Ordertyp, exakte Eingabefeldzuordnung und die anschließende Wertkontrolle. Negative Fälle: falsche ISIN, Kaufseite, doppelte Eingabefelder, geschützte Anmeldemaske.
- **Nicht** übernommen: `StopLossPrefillExecutor.kt`, `StopLossPrefillSession.kt`, `StopLossPrefillActivity.kt`, Mock-Order-Screen als App-Aktivität, Manifest-Berechtigungen oder der Service-Eingabepfad. Die Offline-Simulation ist kein verfügbarer Fernbefehl und darf keine DEGIRO-Order vorbereiten, absenden oder ändern. PR #1790 bleibt als separat überprüfbarer Entwurf offen.

## Abnahme

- `test_android_stable_release_config.py` und JVM-Tests für 9/10-Quarantäne-Scroll versus unverändertes 10/10-Gate, einzelner globaler Order-Launcher, echte Ordermaske, Passwörter und unklare Gold-Seiten.
- Bob-CI, Android-Companion-Lab/Emulator, Risiko und CodeQL vor Merge.
- Echte Samsung-Nachprüfung: Listenbilder erfasst → `LOCAL_RESEARCH_HEADER_SCROLL_SENT` (falls das Suchfeld zunächst fehlt) → `LOCAL_RESEARCH_SEARCH_READY` → exakter ISIN-Text → Produkt `COMPLETE`. Erst dann als real funktionierend melden.
- Server-OCR `MemoryError` und die 9/10-Unvollständigkeit bleiben **separat** offene Probleme; keine indirekte Freigabe durch einen erfolgreichen lokalen Lesetest.

Keine Echtgeldorders. Keine kostenpflichtigen Dienste.
