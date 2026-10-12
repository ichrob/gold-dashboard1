# Zukunft: Walk-forward-Labor und Broker-Vorbereitung

Stand: 2026-10-11. Die Funktion ist ausdrücklich **Forschung, nicht Handel**.

## Implementiert

- GET /api/zukunft/research (nur nach bestehender Bob-Anmeldung). Liest geschlossene 1h-Historie aus Bobs Quellen; bei zu wenig Historie wird kein Sieger behauptet.
- Reproduzierbare historische Simulation auf einem **einzigen, eindeutig bezeichneten Referenzinstrument**. Keine Mischung aus Spot/GC=F/KO-Zertifikat; Kerzen mit offenen oder unmöglichen OHLC-Werten werden ignoriert bzw. abgewiesen. Grössere Zeitlücken blockieren fiktive Trades über die Lücke.
- Sieben Forschungsmodelle: vereinfachte EMA/RSI-Trend-Baseline, strenge und engere Trendfolge, Ausbruch mit und ohne Zusatzbestätigung, Gegenbewegung und deterministisch trainierter logistischer Linearfilter. Der Filter ist **kein Ersatz** für Bobs v7-Live-Logik.
- Rollierende, nicht gemischte **Train → Purge → Validierung → Purge → Out-of-sample-Test**-Fenster (4h Prognosehorizont auf 1h-Bars; 72 Bars Validierung, 72 Bars Test). Das Lernmodell wird ausschliesslich auf vergangenen Trainingsdaten angepasst. Variantenwahl erfolgt nur auf Validierungsdaten, nie auf Testdaten.
- Hypothetische beidseitige Gebühren-/Slippageannahme von 8 Basispunkten je Seite, keine Datenquelle für echte Produktkosten. Einstieg frühestens am nächsten Open, keine überlappenden Positionen. Netto-Simulationsrendite, Testtrades, Profitfaktor, Trefferquote, Drawdown und Datenlücken.
- Ansicht **Zukunft** lädt den Forschungsbericht beim Öffnen; Button für erneuten Abruf. Bestehende vier Paper-Konten bleiben unverändert.
- broker_bridge.py: fail-closed Schnittstellenvertrag für **IBKR** (Kontrakt-ID conid) und **IG Bank** (Markt-ID epic). ISIN-Format mit ISO-6166-Prüfziffer, unmögliche Auftragsausführung, klare Anzeige "nicht verbunden". Weder Keys noch Kontoinformationen noch API-HTTP-Aufrufe werden ausgelöst.

## Automatisierter Hintergrundvergleich (12.10.2026)

- Bobs eigener unabhängiger Hintergrundthread prüft Montag–Freitag ab **08:00 Europe/Zurich** einmal täglich die neue historische 1h-Historie (innerhalb 08–21 Uhr). Die App muss dafür nicht offen sein. Nach Netz- oder Datenfehlern und zu kurzer Historie gibt es mindestens alle 30 Minuten weitere Versuche innerhalb des Handelsfensters. Bei Neustart prüft Bob das Datum des zuletzt gespeicherten Ergebnisses in der Datenbank.
- Reports werden ausschliesslich im bestehenden, privaten PostgreSQL gespeichert: höchstens ein Tagesdatensatz mit sicherem UPSERT, maximal 90 Tage Archiv. Bei einem erneuten Versuch darf eine bereits vollständig ausgewertete Studie nicht zu "insufficient" zurückgestuft werden.
- Die Zukunft-Oberfläche lädt gespeicherte Resultate beim Betreten, aktualisiert sie während längerer Nutzung alle zehn Minuten und zeigt den letzten Tag/Zeitstempel und die archivierten Tagesprüfungen. Der optionale Button lädt **nur den angezeigten Stand neu**; er startet keine rechenintensive Analyse.
- Der Hintergrundprozess verwendet ausschliesslich bestehende freie Marktdaten- und Persistenzkomponenten. Fehlende Quellen oder Archivverbindung werden als unbestätigt gemeldet, niemals still als bestandene Untersuchung interpretiert.
- **Kein autonomes Nachlernen oder Übernehmen in die Live-Strategie; keine Broker-Order.** Die täglichen Berichte sind historische Referenzstudien, keine neue unabhängige Prospektiv-Validierung.

## Noch NICHT implementiert / gesperrt

1. Kein belastbarer **vollständiger** Vergleich der gesamten aktiven Bob-v7-Entscheidungslogik, weil dafür synchronisierte, historisch vollständige 5m/15m/30m/1h/4h-Kerzen und historische Produktauswahl/ISIN-Quoten fehlen. Die Baseline hier ist bewusst als **vereinfachte Forschungsbasis** gekennzeichnet.
2. Die täglichen Referenzberichte werden jetzt im bestehenden privaten Bob-Archiv gespeichert. Eine unabhängige prospektive Versuchsserie und automatische Übernahme lernender Regeln fehlen weiterhin; vier bestehende prospektive Paper-Konten laufen separat.
3. Keine tatsächlich belegten DEGIRO-KO-Einstiege/-Ausstiege in EUR; keine echten Bid/Ask/Finanzierungskosten und keine Nettoergebnisse einer Bank- oder Brokerrechnung.
4. Keine Brokeranmeldung, keine tatsächliche Abfrage von IBKR-/IG-Instrumenten, keine CH-Produktberechtigungsprüfung und keine Test- oder Echtgeldorder. Diese Aufgaben erfordern einen separaten zulässigen Konto-/Demo-Zugang, explizite Erlaubnisse und kontrollierte Paper-API-End-to-End-Tests.

**Wichtig:** Ein erfolgreicher oder besserer historischer OOS-Vergleich allein gibt **weder Handel noch Regelübernahme** frei. Für die Freigabe braucht es unabhängige nachfolgende Paper-Tests, vollständige Kostendaten, KO-/Liquiditätsrisiko, robuste Order/Position-Reconciliation, technische Notabschaltung und gesonderte Zustimmung.

Offizielle Primärdokumente:
- [Interactive Brokers Web API](https://www.interactivebrokers.com/docs/web-api/introduction)
- [Interactive Brokers Trading Web API, Account/Paper-Hinweise](https://www.interactivebrokers.eu/campus/ibkr-api-page/web-api-trading/)
- [IG Bank Schweiz Web APIs](https://www.ig.com/en-ch/trading-platforms/trading-apis/how-to-use-ig-api)

## Tests

python -m unittest -v test_strategy_lab.py

Der reguläre CI-Lauf führt zusätzlich alle test_*.py und test_*.js aus. Es werden weder Broker-Credentials noch kostenpflichtige Dienste installiert.
