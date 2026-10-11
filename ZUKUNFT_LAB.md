# Zukunft: Walk-forward-Labor und Broker-Vorbereitung

Stand: 2026-10-11. Die Funktion ist ausdrücklich **Forschung, nicht Handel**.

## Implementiert

- GET /api/zukunft/research (nur nach bestehender Bob-Anmeldung). Liest geschlossene 1h-Historie aus Bobs Quellen; bei zu wenig Historie wird kein Sieger behauptet.
- Reproduzierbare historische Simulation auf einem **einzigen, eindeutig bezeichneten Referenzinstrument**. Keine Mischung aus Spot/GC=F/KO-Zertifikat; Kerzen mit offenen oder unmöglichen OHLC-Werten werden ignoriert bzw. abgewiesen. Grössere Zeitlücken blockieren fiktive Trades über die Lücke.
- Fünf Forschungsmodelle: vereinfachte EMA/RSI-Trend-Baseline, strenge Trendfolge, Ausbruch, Gegenbewegung und deterministisch trainierter logistischer Linearfilter. Der Filter ist **kein Ersatz** für Bobs v7-Live-Logik.
- Rollierende, nicht gemischte **Train → Purge → Validierung → Purge → Out-of-sample-Test**-Fenster (4h Prognosehorizont auf 1h-Bars; 72 Bars Validierung, 72 Bars Test). Das Lernmodell wird ausschliesslich auf vergangenen Trainingsdaten angepasst. Variantenwahl erfolgt nur auf Validierungsdaten, nie auf Testdaten.
- Hypothetische beidseitige Gebühren-/Slippageannahme von 8 Basispunkten je Seite, keine Datenquelle für echte Produktkosten. Einstieg frühestens am nächsten Open, keine überlappenden Positionen. Netto-Simulationsrendite, Testtrades, Profitfaktor, Trefferquote, Drawdown und Datenlücken.
- Ansicht **Zukunft** lädt den Forschungsbericht beim Öffnen; Button für erneuten Abruf. Bestehende vier Paper-Konten bleiben unverändert.
- broker_bridge.py: fail-closed Schnittstellenvertrag für **IBKR** (Kontrakt-ID conid) und **IG Bank** (Markt-ID epic). ISIN-Format mit ISO-6166-Prüfziffer, unmögliche Auftragsausführung, klare Anzeige "nicht verbunden". Weder Keys noch Kontoinformationen noch API-HTTP-Aufrufe werden ausgelöst.

## Noch NICHT implementiert / gesperrt

1. Kein belastbarer **vollständiger** Vergleich der gesamten aktiven Bob-v7-Entscheidungslogik, weil dafür synchronisierte, historisch vollständige 5m/15m/30m/1h/4h-Kerzen und historische Produktauswahl/ISIN-Quoten fehlen. Die Baseline hier ist bewusst als **vereinfachte Forschungsbasis** gekennzeichnet.
2. Keine dauerhafte persistierte tägliche Versuchsserie/Modellversion in einer unabhängigen Datenbank und keine automatische Übernahme lernender Regeln. Labor läuft bei Aufruf; vier bestehende prospektive Paper-Konten laufen separat.
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
