# Bob – Sonntagsarbeit und Übergabe in den Montags-Livebetrieb

**Stand:** Sonntag, 25. Oktober 2026 (Schweiz). Diese Liste umfasst alle **100** Diagnoseziele des privaten Lesezugriffs. Sie ist eine **Arbeits-/Nachweisplanung**, kein pauschaler Funktions-, Handels- oder Release-Nachweis. Die vollständigen IDs stehen in `sonntag_montag_100_plan.json`; der Validator `diagnoseziele_work_split.py` prüft auf Dopplungen, Lücken und missbräuchliche Statusänderungen.

| Themenblock | Ziele | Bereits unabhängig datiert abgenommen | Sonntag ohne offene Börse | Nächster notwendiger Originalbeleg |
|---|---:|---:|---|---|
| Unabhängige Technik, Code, CI, Archiv, private Diagnose | 24 | 4 (#7, #8, #13, #18) | Ja: Tests, sichere Korrekturen, unabhängige Serverwerte | Je konkretes Ziel, echte Build-/CI-/Live-Beobachtung; nicht pauschal |
| Goldmarkt, Signale und Simulationen mit originalem Marktzeitbezug | 41 | 0 | Statische Regeln, Replays, alte Quellenzeiten, gesicherte Tests | Frische originale Börsen-/Kurs- und Worker-Zeitpunkte, passend zur jeweiligen Session |
| DEGIRO, SnapTrade, Emittenten und Broker-Originalbelege | 22 | 0 | Bestehende CSV-/Screenshot-Reihen, SnapTrade-Lesehistorie, Herkunft/Zeiten, OCR und Negativtests | Exakter Original-Emittent, ISIN/Handelsplatz/Preis inkl. Zeit; kein Schluss aus SnapTrade auf Live-DEGIRO-Ausführung |
| Video-/MCO-Recherche und Veröffentlichung | 7 | 0 | Metadaten, gespeicherte Untertitel/Frames und Videolinks prüfen | Originalpublikationszeit, tatsächlich abrufbares Transkript/Video; Paywall bleibt offen |
| Samsung-Gerät | 5 (#91–95) | 0 | Nur Code-, Android-Build- und Sicherheitstests | Freiwillig bestätigter Funktionstest direkt auf dem Samsung; keine Fernbedienung ohne Auftrag |
| ChatGPT-Client-Tool-Schema | 1 (#1) | 0 | Quell-MCP-Schema prüfen | Anbieter-/Plugin-Tool-Discovery muss Focus-Parameter tatsächlich freigeben |

**Zählung:** 24 + 41 + 22 + 7 + 5 + 1 = 100. Von 100 sind zum historischen Prüfstand **4** individuell datiert abgenommen, **96** nicht vollständig bestätigt. **94** Ziele können zumindest technisch/archivbasiert am Sonntag weiter geprüft werden; das heißt **nicht**, dass all diese Ziele sonntags abgeschlossen werden können. Für die ursprünglichen Markt-Beweisketten dürfen fehlende Sonntagspreise niemals ergänzt, auf Montag rückdatiert oder mit Simulationen gleichgesetzt werden.

## Fertig vorbereitet für den nächsten Live-Datenbetrieb

- Der bereits eingerichtete einmalige Montagstermin ist **26.10.2026, 08:00 Europe/Zurich**. Er prüft nur, was im jeweiligen echten Datenfenster vorliegt. Es wird **keine** Eröffnung von DEGIRO-/Emittentenquotierungen um exakt 08:00 angenommen.
- Erst frische, original datierte Gold-Spot-/CFD-Eingänge, tatsächliche erfolgreiche 30-Sekunden-Bob-Zyklen und ein identischer Analyse-/Anzeigedatensatz bilden einen marktabhängigen Nachweis. Wochenende `paused` ist kein Worker-Ausfall.
- Für KO-/Hebelprodukte sind die tatsächliche ISIN, Long/Short, KO-Schwelle und deren Gültigkeit, originaler Geld-/Briefwert, jeweilige Quellzeit, Währung sowie bestätigter Handelsplatz nötig. Keine Freigabe aus geschätzten, abgelaufenen oder bloß älteren SnapTrade-Daten.
- Push wird getrennt geprüft: Signalereignis → Empfänger → Provider akzeptiert → Samsung sieht Nachricht. Provider-HTTP-201 bestätigt **keine** Gerätezustellung.
- Paper-Fälle mit unbekanntem Originalausstieg bleiben `inconclusive`. Eine spätere Modellquote rekonstruiert keinen realen Geldkurs, ausgeführten Stop oder P/L.
- Neu veröffentlichte GitHub-Änderungen bekommen immer PR-CI, Main-CI und die tatsächlich lesbare Live-SHA als getrennte Nachweise. Ein gemeinsamer bestandener Testsatz ist keine Einzelabnahme von 100 Funktionen.

## Sicherheits- und Freigaberegeln

Keine Echtgeldorder, kein Brokerkauf oder -verkauf, kein Stop/KO/Strategiewechsel, keine neuen Zugriffsrechte oder öffentlicher Datenbankzugang und keine Mail oder Push-Zwischenberichte ohne explizite Zustimmung. Keine automatisierte Samsung-Bedienung. Technische Tests dürfen am Sonntag freigegeben werden, wenn bestehende Sicherheitsgrenzen eingehalten sind; marktgebundene Einzelabnahmen erst mit passenden unabhängigen Originalbelegen.

**Diese Datei ist ein lebender Prüfplan.** Der private Bob-Lesebericht liefert künftig eine komprimierte Verteilung, nicht alle persönlichen Quelleninhalte oder gespeicherte Quoten. Weder die Datei noch die Gruppierung macht einen offenen Punkt automatisch `verified`.
