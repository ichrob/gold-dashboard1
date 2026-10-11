# Bob – Vollautomatisch (Entwicklungskonzept v1)

## Ziel und Trennung
Eigenständige Handelslogik zuerst ausschließlich im Paper-Modus. Bestehende DEGIRO-Assistent- und manuelle Handelsfunktionen bleiben unverändert. Keine inoffizielle DEGIRO-Orderanbindung. Standardmäßig niemals Echtgeldaufträge senden.

## Oberfläche
Eigene Sparte „Vollautomatisch“ mit Entwicklungsstatus, Simulation, Statistik, Fehleranalyse und Brokerfreigabe. Status unterscheidet Design / implementiert / geprüft / live. Niemals simulierte Trades als reale Trades darstellen.

## Daten und Marktentscheidung
Dieselbe zeitlich konsistente Gold-Datenbasis für Marktanalyse und Evaluation: XAU/USD-Spot sowie kontraktspezifischer Future nur mit dokumentierter Basiswert-Zuordnung. Zeitstempel, Verzögerung, Session und Datenqualitäts-Sperren protokollieren. Trendstruktur EMA20/50/200, 5m/15m/30m/1h, MACD, RSI, DMI/ADX, ATR, Fibonacci und Volumen soweit verlässlich verfügbar. Gültige Signale nur bei explizit nachvollziehbarer Regel, sonst ABWARTEN. Whipsaw-Filter und Handelszeitfilter. Laufende Trades erhalten eigene Halte-/Ausstiegslogik.

## Simulationsmotor
Diskrete Order-Zustandsmaschine: CREATED -> ACCEPTED -> PARTIAL/FILLED/REJECTED/CANCELLED -> CLOSED. Eindeutige idempotente Order-ID; verfügbare Liquidität, Bid/Ask, realistische Ausführung, Spread, Gebühren, Slippage, Finanzierungskosten, Knock-out und Handelszeiten. Kein Lookahead: Entscheidung nur auf zum Entscheidungszeitpunkt bekannten Daten. Virtuelles Startkapital konfigurierbar; Vorschlag 100 EUR. Jeden Tick / Signal / Order / Ausführung mit Quellzeit und Systemzeit dauerhaft speichern. Replay aus unveränderbaren Ereignissen. Simulation läuft serverseitig unabhängig vom Browser, sofern Infrastruktur verfügbar; bei Server-/Datenlücken pausieren statt blind fortzusetzen.

## Risiko und Schutz
Kein Eintritt ohne vollständige Produktstammdaten und aktuelle Kurse. Risikobudget pro Trade (zunächst 0.5% des virtuellen Kapitals), Tagesverlustgrenze (2%), Gesamt-Drawdown-Halt (8%), höchstens eine korrelierte Goldposition, Verlust- und Störungs-Kill-Switch, keine automatische Aufstockung nach Verlusten. Für KO-Produkte Stop-Abstände, Gaps und Totalverlustrisiko ausdrücklich berücksichtigen. Vor jedem Orderentscheid Regeln erneut validieren. Limits sind vorläufige Testparameter, keine Anlageempfehlung.

## Evaluation
Zunächst Unit-/Integrationstests der Zustandsmaschine, Stop/Ziel, doppelter Zustellung, Marktpausen, Preisfehler und Serverneustarts. Danach mindestens 30 Handelstage Paper-Forwardtest und verschiedene Marktphasen; Dauer bei unzureichender Stichprobe verlängern. Messgrößen: Netto-PnL, Drawdown, Profit-Faktor, Erwartungswert, Trefferquote, Slippage, Gebühren, risikoadjustierte Rendite, Verfügbarkeit, Regelverletzungen und Ausreißer. Walk-forward und Out-of-sample statt Optimierung auf dieselben Daten. Neue Regeln zunächst Challenger, unabhängige Auswertung, erst danach kontrollierte Promotion.

## Echtgeld-Gate (gesperrt)
Getrennte Brokeradapter-Schnittstelle, nur Broker mit ausdrücklich erlaubter offizieller Handels-API, akzeptablen Kosten und passender Zulassung/Produktpalette. Paper- und Live-Konfiguration technisch getrennt. Echtgeld wird nur nach neuer expliziter Zustimmung mit separater Freischaltung, Limits und manueller Notabschaltung möglich. Kein automatischer Übergang nach positiven Testergebnissen.

## Nächste Umsetzungsschritte
1. Brokerunabhängige Event- und Orderzustandsmaschine samt Tests.
2. Serverpersistenz und idempotenter Job mit Wiederanlauf.
3. Daten- und Signaladapter auf vorhandene Bob-Module.
4. Paper-Orderausführung und Bericht in eigener UI.
5. Testprotokoll, unabhängiger Forwardtest, Freigabeprüfung.
