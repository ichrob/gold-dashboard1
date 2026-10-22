# Bob – neun Arbeitsbereiche, überprüfbarer Stand (22.10.2026)

**Wichtig:** Dieser Bericht ist eine Bestandsaufnahme und kein Nachweis, dass alle neun Bereiche
produktiv vollständig funktionieren. Original-Quellzeiten bleiben unverändert.
Keine Echtgeldorder, Handelsfreigabe, KO-/Stopp- oder Rankingregel geändert.

| Bereich | Nachweis in dieser Änderung | Noch offen / echte Abnahme |
|---|---|---|
| 1. Analyse | Fehlender *prozesslokaler* Evaluator-Mitschnitt erhält expliziten Grund; echte Warnung bleibt bestehen | MTF-Fehler im Browser/Server anhand Request-ID und Marktzeit nachstellen, vollständige Signalausgabe nur bei belegter Frische |
| 2. Kerzen | Quellenuhrzeit, Kerzenintegrität und Nachtmodus bereits im Diagnosevertrag; keine synthetischen OHLC | Beim nächsten Handelsfenster verifizieren, ob 1m/5m wieder frische vollständige Kerzen liefern; 15m/30m gesondert |
| 3. Datenbank | Render-Logs meldeten wiederholt `BOB_AUDIT prospective_unavailable reason=query-timeout`; Datenbank öffentlich nicht erreichbar | Plan/Index über autorisierten *internen* DB-Zugriff prüfen; niemals IP-Allowlist öffnen, um ChatGPT-Zugriff zu erzwingen |
| 4. Goldprodukte | Als `terminated` belegte ISINs in der mobilen Übersicht kompakt; keine aktuellen Werte und kein Entwurf | Auf Samsung prüfen. `terminated` ist nicht zwangsläufig `ausgenockt`; KO-Grund nur mit Originalemittentennachweis behaupten |
| 5. Paper-Trading | Status `paused` enthält den vom Nutzer festgelegten Sitzungsmodus, nicht angeblichen Marktschluss | Beim nächsten 08:00-Start alle fünf Konten, Nettokosten, Datenlücken und vorläufige Ergebnisse prüfen |
| 6. Selbstheilung | Bestehende begrenzte Worker-Neustarts und unabhängige Bestätigung bleiben unverändert | Fehlercodes mit echten Wiederherstellungsevents korrelieren; kein Restart allein ist Behebung |
| 7. Lesezugriff | Bestehende 100-Punkte-Liste ist Inventar: **0 tatsächlich vollständig verifiziert** | Pro Punkt eigenes Akzeptanzkriterium und Einzelnachweis. Kein unberechtigter Geräte-/Konto-/Datenbankzugriff |
| 8. CI/Render | Eigenständiges schreibgeschütztes `tools/bob_release_verify.py <40-Zeichen-Main-SHA>` vergleicht beide öffentlichen /health-Builds; mit Unit Tests | Ein periodischer Lauf kann erst nach separater Prüfung einer *nicht* in Render-checksPass hängenden Automatik freigegeben werden (Issue #783) |
| 9. Samsung | Nur tatsächlich gestartete Bob-Seiten dürfen als Kontext für `nochmal` dienen; Bilder/Einstellungen nicht wiederholbar; Regressionstest | APK-Build/Signatur/Sprachdienst/Gerätetest vor Ort nötig. Kein Fernzugriff, keine DEGIRO-UI-/Echtgeldautomation |

## Beobachtungen beim letzten Bericht

- Beide Render-Dienste: Live-Commit `fc1453b`, Einstellung `checksPass`.
- Bobs private Diagnose: `analysis=unavailable` (das allein ist keine bestätigte globale Evaluatorstörung);
  vier kurze Kerzenrahmen `stale` in der Nutzersession `night`.
- Produktbericht: zehn Identitäten, vier vom Emittenten als beendet gemeldet.
  Kein aktueller ausführbarer DEGIRO-Kurs oder automatische Orderfreigabe.
- Simulationsherzschlag: fünf Konten, außerhalb 08:00–22:00 Schweizer Nutzerfenster `paused`;
  ungeklärte Paperausgänge dürfen nicht als echte Verluste/Erträge verbucht werden.
- Render Push: mehrere `BOB_AUDIT prospective_unavailable reason=query-timeout` im Log.
  Ein guter `/health`-Wert allein widerlegt diese gezielte Query-Fehlermeldung nicht.
- Datenbank Render-Postgres: externe Direktabfragen von dieser Verbindung wegen leerer IP-Allowlist gesperrt;
  keine Anpassung der Sicherheitsfreigabe vorgenommen.

## Freigabekriterien

1. CI inklusive Python-, JS- und Android-Tests grün; Testlauf ist keine Live-Geräteabnahme.
2. Änderungen vor Merge separat geprüft; erst anschließend `main`-CI abwarten.
3. Beide Render-Dienste müssen nach Deploy **exakt** denselben geprüften Main-SHA melden.
4. Ohne frische Originalkurse keine unbelegte Markt-/Produktempfehlung.
5. Reparaturen und hundert Lesepunkte werden erst nach realem Nachweis als `verified` geführt.
