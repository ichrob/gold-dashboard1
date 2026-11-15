# Bob – schneller Einstieg / Hebel / Stop-Loss (prospektive Schattenstudie)

**Start:** Erst ab dem ersten tatsächlichen Worker-Lauf nach Deployment. Keine rückwirkend erfundenen Einstiegskurse oder Orderausführungen. Bestehende November-Konten (`trend800nov`, `normal1000nov`) und ältere Simulationshistorien bleiben unverändert.

## Studienfragen

1. Hätte Bob mit einem eigenständigen schnellen SHORT- oder LONG-Ansatz häufiger an starken Intraday-Bewegungen teilgenommen, auch wenn die bestehende Mehrindikatoranalyse „ABWARTEN“ meldet?
2. Welche der vier eingefrorenen, kausalen Hypothesen ist innerhalb einer gemeinsamen Datenabdeckung vielversprechend: **5m-Ausbruch**, **5m-Impuls**, **Rücksetzer mit Fortsetzung** oder **Impuls unmittelbar nach einem bestätigten hochrelevanten US-Termin**?
3. Was ergeben hypothetische 3×, 5×, 8×, 10×, 15×, 20× und 30× Hebel bei **demselben Signal, demselben beobachteten Ausstieg** und **festem 1%-Risikobudget**?

## Originaldaten und Einstiegsbedingungen

- Dieselbe bereits vorhandene `XAU/USD`-Spotquelle und 120 geschlossene 1m-Kerzen wie im Intraday-Vergleich. Keine Future-/CFD-Verwechslung. Nur ein Quellenidentitätsnachweis, kein Zusammenmischen von Historien.
- Frischer abgeschlossener 5m-Bar (höchstens 90 Sekunden alt) und frischer originaler Spot-Kurs (höchstens 60 Sekunden alt). Keine späteren Barwerte für rückwirkende Signale.
- Ausbruch = Schlusskurs außerhalb des Hochs/Tiefs der vorherigen sechs 5m-Bars mit ATR- und Kerzenkörperfilter. Impuls = ausreichend große Körper- und Schlusskursänderung relativ zu ATR. Rücksetzer = bereits vorliegender Impuls, begrenzter gegenläufiger Bar, danach erneute Fortsetzung. Terminvariante = bestätigter Zeitstempel aus dem offiziellen, aktuellen Wirtschaftskalender plus tatsächlicher anschließender Kursimpuls. Der Kalender kennt keine tatsächliche Nachrichtenüberraschung.
- **Unabhängig** vom `market.direction` und den alten EMA-/MACD-/Stundentrend-Gates. Keine Änderung von Bobs normalen Kauf-/Verkaufs-Empfehlungen.
- Kein Einstieg außerhalb der Forschungs-Handelszeiten oder nach Beobachtungslücken.

## Stop- und Hebelvergleich

- Anfangsstop = jüngstes Strukturhoch/-tief mit 0,2 × ATR-Puffer, wobei der Abstand auf 0,8–3 ATR begrenzt wird; ein Abstand über 5% Spot führt zur Ablehnung.
- Ziel = 2R. Nach beobachtetem Fortschritt von 1R wird der Stop auf Einstand verschärft. Nach 1,5R wird der Stop am besten **beobachteten** Kurs mit 1 ATR Abstand nachgezogen, niemals wieder gelockert.
- Beobachteter Stopdurchbruch, Ziel, maximal 300 Minuten, Handelsschluss oder 30 Minuten ohne mindestens 0,25R Fortschritt beendet die Position. **Exit erfolgt zum nächsten tatsächlich beobachteten Spotpreis**, nicht fiktiv exakt zum Stopwert. Lücken über 90 Sekunden werden als **nicht auswertbar** behandelt.
- Pro Variante ein eigenes virtuelles Startkapital von 1.000 EUR, maximal 65% eingesetztes Kapital und hypothetisches 1%-Risiko bei idealer Stopausführung. Mit höherem Hebel wird deshalb der Euro-Einsatz kleiner. Bei Lücken oder Knock-out kann der Verlust größer sein.
- Zusätzlich zum risikogleichen Vergleich wird ein **separater Gleich-Einsatz-Fall mit 65% Kapital bei jeder Hebelstufe** berechnet: möglicher zusätzlicher Gewinn, entsprechend höherer Verlust am theoretischen Stop und potentieller Totalverlust. Diese aggressive Gegenrechnung verändert keine Portfolio-Kontostände.
- Für eine reine Sensitivitätsrechnung werden 0,6% hypothetische variable Gesamtkosten plus 2 EUR pro Trade angenommen. Diese Zahlen sind **keine verifizierten** DEGIRO-Handelskonditionen.
- Nicht zu übersehende Ergebniskennzeichnung: `productReturnVerified=false`, `fillVerified=false`, `strategyWinnerConfirmed=false`, `realOrders=false`. Ein Multiplikator auf die Goldpreisänderung ist **kein Kurs eines realen Knock-out-Produkts**; ein tatsächlicher Turbo kann bereits vor dem errechneten Stop wertlos werden.

## Laufzeit, Daten und Prüfung

Der neue Worker wird **erst nach dem Commit der bestehenden Papierkonten** separat in einer Fehlerabschirmung ausgeführt. Er verändert keine vorhandenen Paper-Ledger, Live-Signale, Produkt-Rankings, Stop-Orders oder Push-Routen. Versionierter Zustand in `bob_rapid_leverage_state`, abgeschlossene Fälle in `bob_rapid_leverage_cases`; Diagnose-Feld `rapidLeverageStudy` unter Bobs Simulationsbericht. Studie läuft bis zur manuellen Auswertung, maximal 100 Einstiege pro Setup.

`python -m unittest test_rapid_leverage_study.py` prüft Einstiegstiming, Nachrichtenzeitpunkt, relative Hebel-Einsatzgrößen, beobachtete Stopausgänge, Nachziehen, Lücken, Originaldaten und Unveränderlichkeit.

## Noch nicht geliefert: verifizierter DEGIRO-Nettovergleich

Hierfür sind **je ISIN und Zeitpunkt** bestätigte Geld-/Briefkurse, Bezugsverhältnis, KO-Barriere, Produktwährung, Broker-Verfügbarkeit und tatsächliche Ausführungslücken nötig. Eine mathematisch höhere Spot-Proxy-Rendite darf **nicht** als nachgewiesener DEGIRO-Gewinn ausgewiesen werden. Der Screenshot-Verlauf vom **10.11.2026** ist ein historischer Prüf-Anlass, aber keine ex-ante-Handelsausführung; das Tageshoch als exakter Einstieg darf nicht angenommen werden.

Weitere erforderliche Arbeit: Produktquoten-Forward-Paare mit harten KO-/Freigabe-Schranken speichern; Nettovergleich mit Spread, Gebühren, Slippage und FX; Backtest/Walk-forward auf unabhängigen Tagen, Out-of-sample-Verifikation; eigene Anzeige in der Bob-Oberfläche mit klares Proxy/Original-Kennzeichen. Bis dahin **keine automatische Strategiebeförderung und keine Echtgeldorders**.
